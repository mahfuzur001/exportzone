from __future__ import annotations

import logging
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags

from apps.cart.models import Cart
from apps.store.models import ProductVariant
from apps.store.services import CouponError, evaluate_coupon, record_coupon_use

from .models import Order, OrderItem, OrderStatusHistory

logger = logging.getLogger(__name__)
SHIPPING_CHARGE = Decimal("0.00")


class OrderCreationError(Exception):
    """A user-facing order validation error."""


class OrderCancellationError(Exception):
    """A user-facing order cancellation failure."""


def restore_stock_for_order(order: Order) -> int:
    """Put an order's units back into stock and return how many were returned.

    Stock is only deducted at checkout time, so a cancellation has to credit it
    again or the units are lost for good.  The caller must already hold a lock on
    ``order`` (every caller wraps this in ``select_for_update`` + ``atomic``) so
    that two concurrent cancellations cannot both credit the same units.
    """
    items = list(order.items.all())
    if not items:
        return 0
    variants = {
        variant.pk: variant
        for variant in ProductVariant.objects.select_for_update().filter(
            pk__in={item.product_variant_id for item in items}
        )
    }
    restored = 0
    for item in items:
        variant = variants.get(item.product_variant_id)
        if variant is None:
            # OrderItem.product_variant is PROTECT, so this should be unreachable;
            # log rather than fail the cancellation if it ever happens.
            logger.warning(
                "Could not return %s unit(s) of variant %s to stock for order %s.",
                item.quantity,
                item.product_variant_id,
                order.order_number,
            )
            continue
        variant.stock += item.quantity
        variant.save(update_fields=["stock", "updated_at"])
        restored += item.quantity
    return restored


@transaction.atomic
def cancel_order_for_customer(*, order_number, user) -> Order:
    """Cancel a customer's own order and return its units to stock."""
    try:
        order = Order.objects.select_for_update().get(order_number=order_number, user=user)
    except Order.DoesNotExist:
        raise OrderCancellationError("We could not find that order.")
    if order.status == Order.Status.CANCELLED:
        # Already cancelled once; never credit the same units a second time.
        return order
    try:
        order.set_status(Order.Status.CANCELLED)
    except ValidationError as error:
        raise OrderCancellationError("; ".join(error.messages)) from error
    restored = restore_stock_for_order(order)
    order.save(update_fields=["status", "cancelled_at", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order,
        status=Order.Status.CANCELLED,
        note=f"Cancelled by customer. {restored} unit(s) returned to stock." if restored else "Cancelled by customer.",
    )
    return order


def _send_confirmation_safely(order_id: int) -> None:
    try:
        send_order_confirmation_email(order_id)
    except Exception:
        logger.exception("Unexpected order confirmation failure for order %s", order_id)


def generate_order_number() -> str:
    today = date.today().strftime("%Y%m%d")
    for _ in range(10):
        candidate = f"EZ-{today}-{secrets.randbelow(10000):04d}"
        if not Order.objects.filter(order_number=candidate).exists():
            return candidate
    raise OrderCreationError("Could not generate a unique order number. Please try again.")


def _locked_cart_for_user(user):
    try:
        return Cart.objects.select_for_update().get(user=user)
    except Cart.DoesNotExist:
        raise OrderCreationError("Your cart is empty.")


@transaction.atomic
def create_order_from_cart(*, user, checkout_data) -> Order:
    if checkout_data.get("payment_method") != Order.PaymentMethod.COD:
        raise OrderCreationError("Only Cash on Delivery is currently available.")

    cart = _locked_cart_for_user(user)
    cart_items = list(
        cart.items.select_for_update()
        .select_related("product_variant__product")
        .prefetch_related("product_variant__product__images")
    )
    if not cart_items:
        raise OrderCreationError("Your cart is empty.")

    variant_ids = [item.product_variant_id for item in cart_items]
    locked_variants = {
        variant.pk: variant
        for variant in cart_items[0].product_variant.__class__.objects.select_for_update()
        .select_related("product")
        .filter(pk__in=variant_ids)
    }
    subtotal = Decimal("0.00")
    for item in cart_items:
        variant = locked_variants.get(item.product_variant_id)
        if variant is None or not variant.product.is_active:
            raise OrderCreationError("A product in your cart is no longer available.")
        if item.quantity < 1:
            raise OrderCreationError("Cart quantities must be greater than zero.")
        if variant.stock < item.quantity:
            raise OrderCreationError(f"Insufficient stock for {variant.product.name}.")
        subtotal += variant.product.base_price * item.quantity

    # The coupon is validated and its redemption counted inside this same transaction,
    # so a code that runs out while the customer is filling the form is rejected here
    # rather than silently charging full price.
    coupon_code = (checkout_data.get("coupon_code") or "").strip().upper()
    discount = Decimal("0.00")
    coupon = None
    if coupon_code:
        try:
            coupon, discount = evaluate_coupon(
                code=coupon_code, subtotal=subtotal, user=user
            )
        except CouponError as error:
            raise OrderCreationError(str(error))
        # Guard the total itself: even with a valid code the discount can never exceed
        # the subtotal, and shipping is never discounted.
        if discount > subtotal:
            discount = subtotal
        if coupon.is_exhausted:
            raise OrderCreationError("That discount code has just reached its usage limit.")

    order = Order.objects.create(
        order_number=generate_order_number(),
        user=user,
        payment_method=Order.PaymentMethod.COD,
        total_amount=subtotal - discount + SHIPPING_CHARGE,
        shipping_charge=SHIPPING_CHARGE,
        discount_amount=discount,
        coupon_code=coupon.code if coupon else "",
        shipping_full_name=checkout_data["full_name"],
        shipping_phone=checkout_data["phone"],
        shipping_address=checkout_data["address"],
        shipping_area=checkout_data["area"],
        delivery_note=checkout_data.get("delivery_note", ""),
        estimated_delivery=date.today() + timedelta(days=5),
    )
    OrderStatusHistory.objects.create(order=order, status=Order.Status.PENDING, note="Order placed")
    for item in cart_items:
        variant = locked_variants[item.product_variant_id]
        price = variant.product.base_price
        OrderItem.objects.create(
            order=order,
            product_variant=variant,
            product_name_snapshot=variant.product.name,
            size_snapshot=variant.size,
            color_snapshot=variant.color,
            quantity=item.quantity,
            price=price,
            subtotal=price * item.quantity,
        )
        variant.stock -= item.quantity
        variant.save(update_fields=["stock", "updated_at"])

    if coupon is not None:
        record_coupon_use(coupon)

    cart.items.all().delete()
    transaction.on_commit(lambda: _send_confirmation_safely(order.pk))
    return order


def send_order_confirmation_email(order_id: int) -> bool:
    try:
        order = Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
        confirmation_path = reverse("orders:confirmation", kwargs={"order_number": order.order_number})
        context = {
            "order": order,
            "confirmation_url": f"{settings.SITE_URL.rstrip('/')}{confirmation_path}",
        }
        html_body = render_to_string("orders/emails/order_confirmation.html", context)
        email = EmailMultiAlternatives(
            subject=f"Export Zone — Order Confirmation #{order.order_number}",
            body=strip_tags(html_body),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send()
        return True
    except Exception:
        logger.exception("Could not send order confirmation for order %s", order_id)
        return False
