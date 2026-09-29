from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class CustomUserManager(BaseUserManager):
    """Manager that uses the email address as a user's primary identifier."""

    use_in_migrations = True

    def create_user(
        self,
        email: str,
        phone: str,
        full_name: str,
        password: str | None = None,
        **extra_fields: Any,
    ):
        if not email:
            raise ValueError("The email address is required.")
        if not phone:
            raise ValueError("The phone number is required.")
        if not full_name:
            raise ValueError("The full name is required.")
        if password is None:
            raise ValueError("A password is required.")

        user = self.model(
            email=self.normalize_email(email).lower(),
            phone=phone.strip(),
            full_name=full_name.strip(),
            **extra_fields,
        )
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        phone: str,
        full_name: str,
        password: str | None = None,
        **extra_fields: Any,
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, phone, full_name, password, **extra_fields)
