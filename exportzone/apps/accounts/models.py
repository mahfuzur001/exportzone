from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import CustomUserManager


bangladesh_phone_validator = RegexValidator(
    regex=r"^01\d{9}$",
    message="Enter a valid Bangladesh phone number in the format 01XXXXXXXXX.",
)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """The Export Zone account model, authenticated by email or phone."""

    email = models.EmailField(unique=True)
    phone = models.CharField(
        max_length=11,
        unique=True,
        validators=[bangladesh_phone_validator],
    )
    full_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone", "full_name"]

    class Meta:
        ordering = ["-date_joined"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_customuser_unique_email_ci",
            )
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = self.__class__.objects.normalize_email(self.email).lower()
        self.phone = self.phone.strip()
        self.full_name = self.full_name.strip()
        super().save(*args, **kwargs)


class Address(models.Model):
    """A saved delivery address belonging to a customer."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=11, validators=[bangladesh_phone_validator])
    address = models.TextField(max_length=500)
    area = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-updated_at"]
        indexes = [models.Index(fields=["user", "is_default"])]

    def __str__(self):
        return f"{self.full_name} - {self.area}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
