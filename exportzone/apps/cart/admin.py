from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count", "updated_at")
    search_fields = ("user__email", "user__full_name", "user__phone")
    readonly_fields = ("created_at", "updated_at")
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product_variant", "quantity", "updated_at")
    search_fields = ("cart__user__email", "product_variant__sku", "product_variant__product__name")
    list_select_related = ("cart", "product_variant", "product_variant__product")
