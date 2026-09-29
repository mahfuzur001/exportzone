"""Django admin integration for orders.

The store console (``/admin-dashboard/orders/``) owns day-to-day fulfilment, but
staff also work in the Django admin, so the status workflow is enforced here too:
the change form offers only the valid next steps, every change lands in the order
status history, and the customer receives the same status email as before.
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from apps.admin_dashboard.services import change_order_status

from .models import Order, OrderItem, OrderStatusHistory

STATUS_COLOURS = {
    Order.Status.PENDING: "#f59e0b",
    Order.Status.CONFIRMED: "#d4af37",
    Order.Status.PROCESSING: "#38bdf8",
    Order.Status.SHIPPED: "#a78bfa",
    Order.Status.DELIVERED: "#34d399",
    Order.Status.CANCELLED: "#f87171",
}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name_snapshot", "size_snapshot", "color_snapshot", "price", "subtotal")


class OrderStatusHistoryInline(admin.TabularInline):
    """Read-only audit trail, shown underneath the order it belongs to."""

    model = OrderStatusHistory
    extra = 0
    can_delete = False
    fields = ("status", "changed_by", "note", "created_at")
    readonly_fields = fields
    ordering = ("created_at",)

    def has_add_permission(self, request, obj=None):
        return False


class OrderAdminForm(forms.ModelForm):
    """Restrict the status dropdown to the transitions the workflow allows."""

    status_note = forms.CharField(
        required=False,
        max_length=255,
        label="Status note",
        help_text="Stored in the status history when the status changes.",
    )

    class Meta:
        model = Order
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            return
        status_field = self.fields["status"]
        status_field.choices = [
            (self.instance.status, self.instance.get_status_display()),
            *[
                (value, label)
                for value, label in Order.Status.choices
                if self.instance.can_transition_to(value)
            ],
        ]
        status_field.help_text = "Only the next valid steps for this order are listed."


def _bulk_status_action(status, label):
    """Build a changelist action that moves the selected orders to ``status``."""

    def action(modeladmin, request, queryset):
        moved, skipped = [], []
        for order in queryset:
            if not order.can_transition_to(status):
                skipped.append(order.order_number)
                continue
            try:
                change_order_status(
                    order_number=order.order_number,
                    status=status,
                    changed_by=request.user,
                    note=f"Marked as {label} from the Django admin.",
                )
            except ValidationError as error:
                skipped.append(f"{order.order_number} ({error.messages[0]})")
            else:
                moved.append(order.order_number)

        if moved:
            modeladmin.message_user(
                request,
                f"{len(moved)} order(s) marked as {label}: {', '.join(moved)}.",
                messages.SUCCESS,
            )
        if skipped:
            modeladmin.message_user(
                request,
                f"Skipped {len(skipped)} order(s) that cannot move to {label}: {', '.join(skipped)}.",
                messages.WARNING,
            )

    action.__name__ = f"mark_{status.lower()}"
    action.short_description = f"Mark selected orders as {label}"
    return action


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ("order_number", "user", "status_badge", "payment_method", "total_amount", "created_at")
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("order_number", "user__email", "shipping_phone")
    readonly_fields = (
        "order_number",
        "total_amount",
        "shipping_charge",
        "created_at",
        "updated_at",
        "cancelled_at",
        "delivered_at",
    )
    fieldsets = (
        ("Order", {"fields": ("order_number", "user", "status", "status_note")}),
        ("Payment", {"fields": ("payment_method", "total_amount", "shipping_charge")}),
        (
            "Delivery",
            {
                "fields": (
                    "shipping_full_name",
                    "shipping_phone",
                    "shipping_address",
                    "shipping_area",
                    "delivery_note",
                    "estimated_delivery",
                )
            },
        ),
        ("Timeline", {"fields": ("created_at", "updated_at", "cancelled_at", "delivered_at")}),
    )
    list_select_related = ("user",)
    save_on_top = True
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    actions = (
        _bulk_status_action(Order.Status.CONFIRMED, "Confirmed"),
        _bulk_status_action(Order.Status.PROCESSING, "Processing"),
        _bulk_status_action(Order.Status.SHIPPED, "Shipped"),
        _bulk_status_action(Order.Status.DELIVERED, "Delivered"),
        _bulk_status_action(Order.Status.CANCELLED, "Cancelled"),
    )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span style="border:1px solid {0};border-radius:2px;color:{0};padding:2px 8px;'
            'font-size:11px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap">{1}</span>',
            STATUS_COLOURS.get(obj.status, "#d4af37"),
            obj.get_status_display(),
        )

    def save_model(self, request, obj, form, change):
        """Apply status changes through the workflow service, not the raw field."""
        previous_status = None
        if change:
            previous_status = Order.objects.filter(pk=obj.pk).values_list("status", flat=True).first()

        requested_status = form.cleaned_data.get("status") if change else None
        status_changed = bool(
            previous_status and requested_status and requested_status != previous_status
        )
        if status_changed:
            # Keep the stored status untouched and let the service record the move
            # (history entry, timestamps, and the customer email).
            obj.status = previous_status

        super().save_model(request, obj, form, change)

        if not status_changed:
            return

        note = form.cleaned_data.get("status_note") or ""
        if not note:
            note = f"Marked as {dict(Order.Status.choices)[requested_status]} from the Django admin."
        try:
            change_order_status(
                order_number=obj.order_number,
                status=requested_status,
                changed_by=request.user,
                note=note,
            )
        except ValidationError as error:
            messages.error(request, f"Status unchanged: {error.messages[0]}")
        else:
            obj.refresh_from_db(fields=["status", "cancelled_at", "delivered_at", "updated_at"])
            messages.success(
                request,
                f"{obj.order_number} is now {obj.get_status_display()} "
                "and the customer has been notified.",
            )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name_snapshot", "quantity", "price", "subtotal")
    search_fields = ("order__order_number", "product_name_snapshot", "product_variant__sku")
    list_select_related = ("order", "product_variant")
    readonly_fields = ("product_name_snapshot", "size_snapshot", "color_snapshot", "price", "subtotal")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    """Read-only audit log; statuses change on the order page or in the console."""

    list_display = ("order_link", "status_badge", "changed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "changed_by__email", "note")
    list_select_related = ("order", "changed_by")
    fields = ("order_link", "order", "status_badge", "changed_by", "note", "created_at")
    readonly_fields = ("order_link", "order", "status_badge", "changed_by", "note", "created_at")

    @admin.display(description="Order", ordering="order__order_number")
    def order_link(self, obj):
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span style="border:1px solid {0};border-radius:2px;color:{0};padding:2px 8px;'
            'font-size:11px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap">{1}</span>',
            STATUS_COLOURS.get(obj.status, "#d4af37"),
            obj.get_status_display(),
        )
