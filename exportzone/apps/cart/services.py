from __future__ import annotations

from django.db import transaction

from .models import Cart, CartItem


class CartError(Exception):
    """A user-facing cart validation error."""


@transaction.atomic
def add_variant_to_cart(*, user, product, variant, quantity: int) -> CartItem:
    if not product.is_active:
        raise CartError("This product is no longer available.")
    if variant.product_id != product.id:
        raise CartError("That variant does not belong to this product.")
    if quantity < 1:
        raise CartError("Quantity must be at least 1.")

    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    item = CartItem.objects.select_for_update().filter(cart=cart, product_variant=variant).first()
    new_quantity = quantity + (item.quantity if item else 0)
    if variant.stock < 1:
        raise CartError("This variant is out of stock.")
    if new_quantity > variant.stock:
        raise CartError(f"Only {variant.stock} item(s) are available in stock.")

    if item:
        item.quantity = new_quantity
        item.save(update_fields=["quantity", "updated_at"])
    else:
        item = CartItem.objects.create(cart=cart, product_variant=variant, quantity=quantity)
    return item


@transaction.atomic
def update_cart_item(*, user, item_id: int, quantity: int) -> CartItem:
    item = (
        CartItem.objects.select_for_update()
        .select_related("cart", "product_variant")
        .filter(pk=item_id, cart__user=user)
        .first()
    )
    if item is None:
        raise CartError("Cart item not found.")
    if quantity < 1:
        raise CartError("Quantity must be at least 1.")
    if item.product_variant.stock < 1:
        raise CartError("This item is now out of stock.")
    if quantity > item.product_variant.stock:
        raise CartError(f"Only {item.product_variant.stock} item(s) are available in stock.")

    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item
