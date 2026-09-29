from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Sum
from django.core.exceptions import ValidationError

from apps.store.models import ProductVariant


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Cart for {self.user}"

    @classmethod
    def for_user(cls, user):
        return cls.objects.get_or_create(user=user)[0]

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.items.all()), Decimal("0.00"))

    @property
    def shipping(self) -> Decimal:
        return Decimal("0.00")

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.shipping

    @property
    def item_count(self) -> int:
        return self.items.aggregate(total=Sum("quantity"))["total"] or 0


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product_variant"],
                name="unique_cart_item_variant",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="cart_item_quantity_gte_one",
            ),
        ]

    def __str__(self):
        return f"{self.product_variant} x {self.quantity}"

    def clean(self):
        super().clean()
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})

    @property
    def unit_price(self) -> Decimal:
        return self.product_variant.product.base_price

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity
