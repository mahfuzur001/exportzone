from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags

from apps.orders.models import Order, OrderStatusHistory
from apps.orders.services import restore_stock_for_order

logger = logging.getLogger(__name__)

STATUS_EMAIL_SUBJECTS = {
    Order.Status.CONFIRMED: "Export Zone — Order Confirmed #{order_number}",
    Order.Status.PROCESSING: "Export Zone — Order Processing #{order_number}",
    Order.Status.SHIPPED: "Export Zone — Order Shipped #{order_number}",
    Order.Status.DELIVERED: "Export Zone — Order Delivered #{order_number}",
    Order.Status.CANCELLED: "Export Zone — Order Cancelled #{order_number}",
}


def _send_status_update_safely(order_id: int, status: str) -> None:
    try:
        send_order_status_update_email(order_id, status)
    except Exception:
        logger.exception("Unexpected order status email failure for order %s", order_id)


def send_order_status_update_email(order_id: int, status: str) -> bool:
    subject_template = STATUS_EMAIL_SUBJECTS.get(status)
    if not subject_template:
        return False
    try:
        order = Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
        detail_path = reverse("orders:detail", kwargs={"order_number": order.order_number})
        context = {
            "order": order,
            "status": status,
            "status_label": order.get_status_display(),
            "order_url": f"{settings.SITE_URL.rstrip('/')}{detail_path}",
        }
        html_body = render_to_string("orders/emails/order_status_update.html", context)
        email = EmailMultiAlternatives(
            subject=subject_template.format(order_number=order.order_number),
            body=strip_tags(html_body),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send()
        return True
    except Exception:
        logger.exception("Could not send status update email for order %s", order_id)
        return False


def _restock_note(note: str, restored: int) -> str:
    """Append the returned-unit count to a status note without losing the original text."""
    suffix = f"{restored} unit(s) returned to stock."
    return f"{note} {suffix}".strip()[:255] if note else suffix


@transaction.atomic
def change_order_status(*, order_number, status, changed_by, note=""):
    order = Order.objects.select_for_update().get(order_number=order_number)
    previous_status = order.status
    order.set_status(status)
    # Cancelling gives the units back: they were only ever deducted at checkout.
    if status == Order.Status.CANCELLED and status != previous_status:
        restored = restore_stock_for_order(order)
        if restored:
            note = _restock_note(note, restored)
    order.save(update_fields=["status", "cancelled_at", "delivered_at", "updated_at"])
    OrderStatusHistory.objects.create(order=order, status=status, changed_by=changed_by, note=note)
    if status != previous_status:
        order_id = order.pk
        new_status = status
        transaction.on_commit(lambda: _send_status_update_safely(order_id, new_status))
    return order
