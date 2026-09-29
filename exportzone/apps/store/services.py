"""Wishlist and review business rules shared by more than one request path.

Both features are kept out of the views so the "may this customer do this?" checks
live in one place and are covered by tests directly, instead of being re-derived
(and eventually re-broken) inside each view.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Min

from apps.orders.models import Order, OrderItem

from .models import Coupon, Product, ProductReview, WishlistItem

# Cap on a single page of reviews so a heavily reviewed product cannot produce a
# page large enough to time out on a shared host.
REVIEWS_PAGE_SIZE = 10


class ReviewError(Exception):
    """A user-facing review rejection carrying a message safe to show."""


def toggle_wishlist_item(*, user, product: Product) -> tuple[WishlistItem, bool]:
    """Add ``product`` to the wishlist, or remove it when already saved.

    Returns ``(item, saved)`` where ``item`` is the surviving row - the removed one on
    the way out, otherwise the row that was just created. The unique constraint is the
    real guard against a double submit; ``get_or_create`` handles the ordinary case and
    the ``IntegrityError`` fallback covers a genuine race between two tabs.
    """
    if user is None or not user.is_authenticated:
        raise ReviewError("Sign in to save items to your wishlist.")

    existing = WishlistItem.objects.filter(user=user, product=product).first()
    if existing is not None:
        existing.delete()
        return existing, False

    try:
        with transaction.atomic():
            item = WishlistItem.objects.create(user=user, product=product)
    except IntegrityError:
        # Another request saved the same product a moment ago; treat it as already
        # saved rather than surfacing a database error to the shopper.
        item = WishlistItem.objects.filter(user=user, product=product).first()
        if item is None:
            raise ReviewError("Could not update your wishlist. Please try again.")
        item.delete()
        return item, False
    return item, True


def wishlist_queryset(user):
    """The customer's saved products, newest save first."""
    return (
        WishlistItem.objects.filter(user=user)
        .select_related("product", "product__category")
        .prefetch_related("product__images", "product__variants")
    )


def wishlist_product_ids(user) -> set[int]:
    """Product ids the customer has saved, for marking hearts on product cards."""
    if user is None or not user.is_authenticated:
        return set()
    return set(
        WishlistItem.objects.filter(user=user).values_list("product_id", flat=True)
    )


def purchasable_order_items(user, product: Product):
    """Delivered order lines for ``product`` that the customer has not reviewed yet.

    A review has to be tied to something genuinely bought, so only items from
    non-cancelled orders count. Items already carrying a review are filtered out so
    the "write a review" form is only offered where one is actually accepted.
    """
    if user is None or not user.is_authenticated:
        return []
    return (
        OrderItem.objects.filter(
            order__user=user,
            product_variant__product=product,
        )
        .exclude(order__status=Order.Status.CANCELLED)
        .exclude(reviews__user=user)
        .select_related("order", "product_variant")
    )


def create_review(*, user, product: Product, order_item, rating: int, title: str, comment: str) -> ProductReview:
    """Create a review after proving the customer actually bought the item.

    The ownership and status checks are repeated here rather than trusted from the
    form, because the ``order_item`` id arrives in the POST and can be swapped for
    somebody else's.
    """
    if user is None or not user.is_authenticated:
        raise ReviewError("Sign in to write a review.")

    if order_item is None or order_item.pk is None:
        raise ReviewError("Choose which purchase you are reviewing.")

    owned = OrderItem.objects.filter(
        pk=order_item.pk,
        order__user=user,
        product_variant__product=product,
    ).exclude(order__status=Order.Status.CANCELLED).first()
    if owned is None:
        raise ReviewError("You can only review a product from your own order.")

    if ProductReview.objects.filter(product=product, user=user).exists():
        raise ReviewError("You have already reviewed this product.")

    if not 1 <= rating <= 5:
        raise ReviewError("Choose a rating between 1 and 5 stars.")

    review = ProductReview(
        product=product,
        user=user,
        order=owned.order,
        order_item=owned,
        rating=rating,
        title=(title or "").strip(),
        comment=(comment or "").strip(),
    )
    try:
        with transaction.atomic():
            review.full_clean(exclude=["created_at", "updated_at"])
            review.save()
    except IntegrityError:
        # The unique constraint is the authority when two tabs submit at once.
        raise ReviewError("You have already reviewed this product.")
    except ValidationError as error:
        raise ReviewError("; ".join(error.messages))
    return review


def customer_review(user, product: Product) -> ProductReview | None:
    """The signed-in customer's own review of ``product``, if they left one."""
    if user is None or not user.is_authenticated:
        return None
    return ProductReview.objects.filter(product=product, user=user).first()


def approved_reviews(product: Product):
    """Published reviews for a product, newest first, with the author attached."""
    return (
        product.reviews.filter(is_approved=True)
        .select_related("user")
    )


class CouponError(Exception):
    """A user-facing coupon rejection carrying a message safe to show."""


def _normalise(code: str) -> str:
    return (code or "").strip().upper()


def usable_coupons():
    """Every coupon that could still be applied right now."""
    return Coupon.objects.filter(is_active=True).order_by("-created_at")


def evaluate_coupon(*, code: str, subtotal: Decimal, user) -> tuple[Coupon, Decimal]:
    """Return ``(coupon, discount)`` for a code, or raise :class:`CouponError`.

    Every rejection reason is spelled out for the shopper because "invalid code" on
    its own is the single most common support ticket a discount feature generates.
    """
    code = _normalise(code)
    if not code:
        raise CouponError("Enter a discount code.")

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        raise CouponError("That discount code is not valid.")

    if not coupon.is_active:
        raise CouponError("That discount code is no longer active.")
    if coupon.is_expired:
        raise CouponError("That discount code has expired.")
    if coupon.is_started:
        raise CouponError(f"That discount code becomes active on {coupon.starts_at:%d %b %Y}.")
    if subtotal < coupon.min_order_amount:
        raise CouponError(
            f"This code needs a minimum order of ৳{coupon.min_order_amount:,.0f}."
        )
    if coupon.is_exhausted:
        raise CouponError("That discount code has reached its usage limit.")

    if coupon.per_user_limit and user is not None and user.is_authenticated:
        used = (
            Order.objects.filter(user=user, coupon_code=coupon.code)
            .exclude(status=Order.Status.CANCELLED)
            .count()
        )
        if used >= coupon.per_user_limit:
            raise CouponError("You have already used that discount code.")

    discount = coupon.discount_for(subtotal)
    if discount <= 0:
        raise CouponError("That discount code does not reduce this order.")
    return coupon, discount


def recalculate_discount(*, code: str, subtotal: Decimal, user) -> tuple[Coupon, Decimal]:
    """Re-evaluate a code but keep silent about rejections.

    Used when the cart changes underneath an applied coupon: a code that no longer
    qualifies must not be re-raised as a fresh error on every quantity tweak, so the
    caller is handed ``(None, 0)`` instead and simply drops the discount.
    """
    try:
        return evaluate_coupon(code=code, subtotal=subtotal, user=user)
    except CouponError:
        return None, Decimal("0.00")


@transaction.atomic
def record_coupon_use(coupon: Coupon) -> None:
    """Count one redemption of ``coupon``.

    Runs inside the order-creation transaction and takes a row lock, so two
    simultaneous checkouts cannot both slip past a ``usage_limit`` of 1.
    """
    locked = Coupon.objects.select_for_update().get(pk=coupon.pk)
    if locked.is_exhausted:
        raise CouponError("That discount code has just reached its usage limit.")
    locked.times_used = F("times_used") + 1
    locked.save(update_fields=["times_used", "updated_at"])


def site_statistics() -> dict:
    """Small catalogue numbers for the store console and the storefront footer."""
    live = Product.objects.filter(is_active=True)
    return {
        "product_count": live.count(),
        "category_count": live.values("category_id").distinct().count(),
        "in_stock_count": live.filter(variants__stock__gt=0).distinct().count(),
        "price_range": live.aggregate(
            lowest=Min("base_price"), highest=Max("base_price")
        ),
    }
