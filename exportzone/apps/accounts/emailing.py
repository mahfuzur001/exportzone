from __future__ import annotations

import logging
import re
from html import unescape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags


logger = logging.getLogger(__name__)


def _plain_text_body(html_body: str) -> str:
    """Collapse the branded HTML into a readable plain-text alternative."""
    return re.sub(r"\n\s*\n+", "\n\n", unescape(strip_tags(html_body))).strip()


def send_welcome_email(user) -> bool:
    """Send the branded "account created" email without leaking mail errors."""
    site_url = settings.SITE_URL.rstrip("/")
    context = {
        "user": user,
        "shop_url": f"{site_url}{reverse('store:shop')}",
        "login_url": f"{site_url}{reverse('accounts:login')}",
        "contact_url": f"{site_url}{reverse('store:contact')}",
    }
    html_body = render_to_string("accounts/emails/welcome_email.html", context)
    text_body = (
        f"{_plain_text_body(html_body)}\n\n"
        f"Start shopping: {context['shop_url']}\n"
        f"Sign in: {context['login_url']}\n"
        f"Questions? {context['contact_url']}"
    )

    try:
        email = EmailMultiAlternatives(
            subject="Welcome to EXPORT ZONE — your account is ready",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send()
        return True
    except Exception:
        logger.exception("Could not send the welcome email for user %s", user.pk)
        return False
