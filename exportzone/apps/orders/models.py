from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.store.models import ProductVariant


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PROCESSING = "PROCESSING", "Processing"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentMethod(models.TextChoices):
        COD = "COD", "Cash on Delivery"
        BKASH = "BKASH", "bKash"
        NAGAD = "NAGAD", "Nagad"

    STATUS_FLOW = {
        Status.PENDING: {Status.CONFIRMED, Status.CANCELLED},
        Status.CONFIRMED: {Status.PROCESSING, Status.CANCELLED},
        Status.PROCESSING: {Status.SHIPPED, Status.CANCELLED},
        Status.SHIPPED: {Status.DELIVERED},
        Status.DELIVERED: set(),
        Status.CANCELLED: set(),
    }

    order_number = models.CharField(max_length=24, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    # The discount is copied onto the order at checkout so later coupon edits never
    # rewrite what the customer was already charged. nullable=True on an existing
    # SQLite column would rebuild the table, so the default keeps the migration cheap.
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    coupon_code = models.CharField(max_length=40, blank=True)
    shipping_full_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=11)
    shipping_address = models.TextField()
    shipping_area = models.CharField(max_length=120)
    delivery_note = models.TextField(blank=True)
    estimated_delivery = models.DateField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return self.order_number

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.items.all()), Decimal("0.00"))

    def clean(self):
        super().clean()
        if self.payment_method != self.PaymentMethod.COD:
            raise ValidationError({"payment_method": "Only Cash on Delivery is currently available."})
        if self.shipping_charge < 0:
            raise ValidationError({"shipping_charge": "Shipping charge cannot be negative."})
        if self.discount_amount < 0:
            raise ValidationError({"discount_amount": "The discount cannot be negative."})
        # A discount larger than what the items add up to would make the payable
        # total negative, which no payment or cash-on-delivery handover can honour.
        if self.discount_amount > self.subtotal:
            raise ValidationError({"discount_amount": "The discount cannot exceed the order subtotal."})

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.STATUS_FLOW.get(self.status, set())

    def set_status(self, new_status: str):
        if new_status == self.status:
            return
        if not self.can_transition_to(new_status):
            raise ValidationError(f"Cannot change status from {self.get_status_display()} to {dict(self.Status.choices).get(new_status, new_status)}.")
        self.status = new_status
        if new_status == self.Status.CANCELLED:
            self.cancelled_at = timezone.now()
        elif new_status == self.Status.DELIVERED:
            self.delivered_at = timezone.now()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="order_items")
    product_name_snapshot = models.CharField(max_length=180)
    size_snapshot = models.CharField(max_length=8)
    color_snapshot = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="order_item_quantity_gte_one"),
            models.CheckConstraint(condition=models.Q(price__gte=0), name="order_item_price_gte_zero"),
        ]

    def __str__(self):
        return f"{self.product_name_snapshot} x {self.quantity}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["order", "created_at"])]

    def __str__(self):
        return f"{self.order.order_number}: {self.get_status_display()}"
