from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import bangladesh_phone_validator


SIZE_CHOICES = [
    ("XS", "XS"),
    ("S", "S"),
    ("M", "M"),
    ("L", "L"),
    ("XL", "XL"),
    ("XXL", "XXL"),
    ("28", "28"),
    ("30", "30"),
    ("32", "32"),
    ("34", "34"),
    ("36", "36"),
    ("38", "38"),
    ("40", "40"),
    ("42", "42"),
]

COLOR_CHOICES = [
    ("BLACK", "Black"),
    ("NAVY", "Navy"),
    ("BLUE", "Blue"),
    ("LIGHT_BLUE", "Light Blue"),
    ("WHITE", "White"),
    ("GRAY", "Gray"),
    ("CHARCOAL", "Charcoal"),
    ("GREEN", "Green"),
    ("OLIVE", "Olive"),
    ("RED", "Red"),
    ("BEIGE", "Beige"),
    ("BROWN", "Brown"),
]


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/%Y/%m/%d/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "featured"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.base_price < Decimal("0"):
            raise ValidationError({"base_price": "Price cannot be negative."})
        if not self.slug:
            self.slug = slugify(self.name)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self.full_clean(exclude=["created_at", "updated_at"])
        super().save(*args, **kwargs)

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()

    @property
    def available_sizes(self):
        return sorted(
            {variant.size for variant in self.variants.filter(stock__gt=0).only("size")},
            key=lambda s: SIZE_CHOICES.index((s, s)) if (s, s) in SIZE_CHOICES else 99,
        )

    @property
    def available_colors(self):
        return sorted(
            {variant.color for variant in self.variants.filter(stock__gt=0).only("color")},
            key=lambda c: next((i for i, choice in enumerate(COLOR_CHOICES) if choice[0] == c), 99),
        )

    @property
    def rating_summary(self):
        """Average rating and review count, shown on cards and the detail page.

        Computed from approved reviews only, so a pending moderation decision never
        changes the number a shopper sees.
        """
        approved = self.reviews.filter(is_approved=True)
        aggregate = approved.aggregate(average=Avg("rating"), total=Count("id"))
        return {
            "average": round(aggregate["average"], 1) if aggregate["average"] else Decimal("0"),
            "count": aggregate["total"] or 0,
        }

    @property
    def is_low_stock(self) -> bool:
        """True when the product can still be bought but stock is running out."""
        from django.conf import settings as django_settings

        threshold = getattr(django_settings, "LOW_STOCK_THRESHOLD", 5)
        total = sum(variant.stock for variant in self.variants.all())
        return 0 < total <= threshold


class ProductReview(models.Model):
    """A customer rating for a product.

    Reviews are tied to a real order item so a shopper can only review something
    they actually bought, and a product can never collect more than one review per
    customer (the unique constraint enforces that even under a double submit).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(max_length=1000, blank=True)
    is_approved = models.BooleanField(
        default=True,
        help_text="Unapproved reviews are hidden from the storefront until a moderator approves them.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        # One review per product per customer, so a shopper cannot pad the average.
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"],
                name="unique_review_per_product_per_user",
            )
        ]
        indexes = [
            models.Index(fields=["product", "is_approved"]),
            models.Index(fields=["is_approved", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.rating}/5 by {self.user}"

    @property
    def stars(self):
        return range(self.rating, 0, -1)

    def clean(self):
        super().clean()
        # The order item must genuinely belong to both the order and the product,
        # otherwise a crafted POST could attach a review to an unrelated product.
        if self.order_item_id and self.order_item.product_id != self.product_id:
            raise ValidationError("This review does not match the product.")
        if self.order_id and self.order.user_id != self.user_id:
            raise ValidationError("This review does not match the customer.")


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/%d/")
    alt_text = models.CharField(max_length=150, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"{self.product.name} image"

    def save(self, *args, **kwargs):
        if self.is_primary:
            ProductImage.objects.filter(product=self.product).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=8, choices=SIZE_CHOICES)
    color = models.CharField(max_length=30, choices=COLOR_CHOICES)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product", "size", "color"]
        constraints = [
            models.UniqueConstraint(fields=["product", "size", "color"], name="unique_variant_per_product_size_color")
        ]
        indexes = [models.Index(fields=["product", "stock"])]

    def __str__(self):
        return f"{self.product.name} - {self.size} / {self.color}"

    def clean(self):
        super().clean()
        if self.stock < 0:
            raise ValidationError({"stock": "Stock cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["created_at", "updated_at"])
        super().save(*args, **kwargs)


class ContactMessage(models.Model):
    """A message submitted through the public contact form."""

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(
        max_length=11,
        blank=True,
        validators=[bangladesh_phone_validator],
    )
    message = models.TextField(max_length=2000)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_read", "created_at"])]

    def __str__(self):
        return f"{self.name} <{self.email}> ({self.created_at:%Y-%m-%d %H:%M})"


class WishlistItem(models.Model):
    """A product a customer has saved for later.

    Guests are handled by the session layer; once signed in the picks belong to the
    account, so the wishlist follows the customer to another device.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_items")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_wishlist_item_per_user_product",
            )
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.user} saved {self.product.name}"


class Coupon(models.Model):
    """A discount code that can be applied at checkout.

    The amount taken off is copied onto the order when the code is used, so editing
    a coupon later never rewrites what a customer was already charged.
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage off"
        FIXED = "FIXED", "Fixed amount off"

    code = models.CharField(max_length=40, unique=True)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(
        max_length=12,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    max_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Caps a percentage discount. Leave empty for no cap.",
    )
    usage_limit = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="How many times this code may be used in total. Leave empty for unlimited.",
    )
    times_used = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(
        default=1,
        help_text="How many times a single customer may use this code.",
    )
    starts_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_active", "expires_at"])]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.full_clean(exclude=["created_at", "updated_at"])
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.discount_value <= 0:
            raise ValidationError({"discount_value": "Discount must be greater than zero."})
        if self.discount_type == self.DiscountType.PERCENTAGE and self.discount_value > 100:
            raise ValidationError({"discount_value": "A percentage discount cannot exceed 100."})
        if self.max_discount_amount is not None and self.max_discount_amount < 0:
            raise ValidationError({"max_discount_amount": "The cap cannot be negative."})
        if self.starts_at and self.expires_at and self.starts_at > self.expires_at:
            raise ValidationError({"expires_at": "The expiry date must come after the start date."})

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_started(self) -> bool:
        return bool(self.starts_at and self.starts_at > timezone.now())

    @property
    def is_usable(self) -> bool:
        return self.is_active and not self.is_expired and self.is_started

    @property
    def is_exhausted(self) -> bool:
        return bool(self.usage_limit and self.times_used >= self.usage_limit)

    def discount_for(self, subtotal: Decimal) -> Decimal:
        """Return the amount to take off ``subtotal``, never more than the subtotal."""
        if subtotal <= 0:
            return Decimal("0.00")
        if self.discount_type == self.DiscountType.PERCENTAGE:
            amount = subtotal * self.discount_value / Decimal("100")
            if self.max_discount_amount is not None:
                amount = min(amount, self.max_discount_amount)
        else:
            amount = self.discount_value
        # Rounded down to the paisa so rounding can never push the discount above the
        # subtotal and turn the order total negative.
        return min(amount.quantize(Decimal("0.01"), rounding="ROUND_DOWN"), subtotal)
