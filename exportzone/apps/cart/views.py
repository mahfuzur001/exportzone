from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.store.models import Product, ProductVariant

from .models import Cart, CartItem
from .services import CartError, add_variant_to_cart, update_cart_item


@login_required
def cart_detail(request):
    cart = Cart.objects.select_related("user").filter(user=request.user).first()
    if cart is None:
        cart = Cart(user=request.user)
        cart.save()
    cart.items_data = list(
        cart.items.select_related(
            "product_variant__product",
            "product_variant__product__category",
        ).prefetch_related("product_variant__product__images")
    )
    return render(request, "cart/cart.html", {"cart": cart, "cart_items": cart.items_data})


@require_POST
def add_to_cart(request):
    next_url = request.POST.get("next")
    if not request.user.is_authenticated:
        safe_next = next_url if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ) else reverse("store:shop")
        return redirect(f"{reverse('accounts:login')}?{urlencode({'next': safe_next})}")

    product = get_object_or_404(Product, pk=request.POST.get("product_id"), is_active=True)
    variant = get_object_or_404(ProductVariant, pk=request.POST.get("variant_id"), product=product)
    try:
        quantity = int(request.POST.get("quantity", "1"))
    except (TypeError, ValueError):
        quantity = 0

    try:
        add_variant_to_cart(user=request.user, product=product, variant=variant, quantity=quantity)
    except CartError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"{product.name} was added to your cart.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(reverse("store:product_detail", kwargs={"slug": product.slug}))


@login_required
@require_POST
def update_item(request, item_id):
    try:
        quantity = int(request.POST.get("quantity", "0"))
    except (TypeError, ValueError):
        quantity = 0
    try:
        update_cart_item(user=request.user, item_id=item_id, quantity=quantity)
    except CartError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Cart quantity updated.")
    return redirect("cart:detail")


@login_required
@require_POST
def remove_item(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, "Item removed from your cart.")
    return redirect("cart:detail")


@login_required
@require_POST
def clear_cart(request):
    Cart.objects.filter(user=request.user).delete()
    messages.success(request, "Your cart has been cleared.")
    return redirect("cart:detail")
