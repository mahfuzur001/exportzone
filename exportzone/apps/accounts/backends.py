from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrPhoneBackend(ModelBackend):
    """Authenticate an active account with either its email or phone number."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identity = (username or kwargs.get("email") or kwargs.get("phone") or "").strip()
        if not identity or password is None:
            return None

        user_model = get_user_model()
        user = (
            user_model.objects.filter(
                Q(email__iexact=identity) | Q(phone=identity)
            )
            .order_by("pk")
            .first()
        )
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
