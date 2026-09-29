from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.store.services import CouponError, evaluate_coupon

from .forms import CheckoutForm
from .models import Order
from .services import OrderCancellationError, OrderCreationError, cancel_order_for_customer, create_order_from_cart

# Where the code the shopper is currently trying lives between requests.
COUPON_SESSION_KEY = "checkout_coupon_code"


def _cart_snapshot(user):
    """The cart lines plus the subtotal, shared by the page and the coupon preview."""
    cart = getattr(user, "cart", None)
    items = [] if cart is None else list(
        cart.items.select_related("product_variant__product").prefetch_related("product_variant__product__images")
    )
    return items, sum((item.subtotal for item in items), Decimal("0.00"))


def _remember_coupon(request, code: str) -> None:
    """Keep the applied code in the session so it survives the redirect.

    ``apply_coupon`` is a separate POST that only reports whether a code is worth
    anything; without storing the choice the shopper would be bounced back to a blank
    field and the discount would never reach the order.
    """
    if code:
        request.session[COUPON_SESSION_KEY] = code
    else:
        request.session.pop(COUPON_SESSION_KEY, None)


@login_required
def checkout(request):
    addresses = request.user.addresses.all()
    default_address = addresses.filter(is_default=True).first() or addresses.first()
    form = CheckoutForm(request.POST or None)
    if request.method == "GET":
        form.initial.update({"full_name": request.user.full_name, "phone": request.user.phone})
        if default_address is not None:
            form.initial.update(
                {
                    "full_name": default_address.full_name,
                    "phone": default_address.phone,
                    "address": default_address.address,
                    "area": default_address.area,
                }
            )
    if request.method == "POST" and form.is_valid():
        # The code is copied into the session so a validation failure on the address
        # fields does not silently drop a discount the customer legitimately applied.
        _remember_coupon(request, form.cleaned_data.get("coupon_code", ""))
        try:
            order = create_order_from_cart(user=request.user, checkout_data=form.cleaned_data)
        except OrderCreationError as error:
            form.add_error(None, str(error))
        else:
            _remember_coupon(request, "")
            messages.success(request, "Your order was placed successfully.")
            return redirect("orders:confirmation", order_number=order.order_number)

    cart_items, subtotal = _cart_snapshot(request.user)
    if not cart_items and request.method == "GET":
        messages.info(request, "Your cart is empty.")
        return redirect("cart:detail")

    # The applied code is previewed on every render, including a re-render after a
    # validation failure, so the shopper never loses a discount they legitimately
    # applied while fixing an address. An unusable code is dropped silently here - the
    # authoritative check runs inside create_order_from_cart.
    applied_code = (form.data.get("coupon_code") or request.session.get(COUPON_SESSION_KEY) or "")
    applied_code = applied_code.strip().upper()
    discount = Decimal("0.00")
    coupon_message = ""
    if applied_code:
        try:
            _, discount = evaluate_coupon(
                code=applied_code, subtotal=subtotal, user=request.user
            )
        except CouponError as error:
            coupon_message = str(error)
            discount = Decimal("0.00")
            # A code that no longer qualifies must not linger in the session and keep
            # re-raising the same complaint on every later render.
            if request.method == "POST":
                _remember_coupon(request, "")
        else:
            form.fields["coupon_code"].initial = applied_code
            if not form.is_bound or not form.errors:
                form.initial["coupon_code"] = applied_code

    shipping = Decimal("0.00")
    return render(
        request,
        "orders/checkout.html",
        {
            "form": form,
            "cart_items": cart_items,
            "addresses": addresses,
            "subtotal": subtotal,
            "discount": discount,
            "coupon_message": coupon_message,
            "shipping": shipping,
            "total": subtotal - discount + shipping,
        },
    )


@login_required
@require_POST
def apply_coupon(request):
    """Preview a discount code so the shopper sees the new total before committing.

    This is a read-only check: nothing is reserved or counted here, so a customer can
    try codes as often as they like without consuming a redemption.
    """
    code = (request.POST.get("coupon_code") or "").strip().upper()
    _, subtotal = _cart_snapshot(request.user)
    if not code:
        _remember_coupon(request, "")
        messages.info(request, "Enter a discount code first.")
    else:
        try:
            _, discount = evaluate_coupon(code=code, subtotal=subtotal, user=request.user)
        except CouponError as error:
            # Drop the rejected code so a later cart change cannot keep re-raising it.
            _remember_coupon(request, "")
            messages.error(request, str(error))
        else:
            _remember_coupon(request, code)
            messages.success(
                request,
                f"{code} applied. You save ৳{discount:,.2f} on this order.",
            )
    return redirect("orders:checkout")


@login_required
def confirmation(request, order_number):
    order = get_object_or_404(
        Order.objects.filter(user=request.user).prefetch_related("items"),
        order_number=order_number,
    )
    return render(request, "orders/order_confirmation.html", {"order": order})


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    page_obj = Paginator(orders, 10).get_page(request.GET.get("page"))
    return render(request, "orders/order_list.html", {"page_obj": page_obj, "orders": page_obj.object_list})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.filter(user=request.user).select_related("user").prefetch_related("items"),
        order_number=order_number,
    )
    return render(request, "orders/order_detail.html", {"order": order, "status_choices": Order.Status.choices})


@login_required
@require_POST
def cancel_order(request, order_number):
    get_object_or_404(Order.objects.filter(user=request.user), order_number=order_number)
    try:
        cancel_order_for_customer(order_number=order_number, user=request.user)
    except OrderCancellationError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Your order was cancelled and the items are back in stock.")
    return redirect("orders:detail", order_number=order_number)
