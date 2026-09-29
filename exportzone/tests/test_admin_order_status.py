"""Django admin order-status workflow: dropdown, history, email, bulk actions."""

import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.store.models import Category, Product, ProductVariant


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AdminOrderStatusTests(TestCase):
    """Staff must be able to move an order forward from the Django admin."""

    password = "A-strong-passphrase-42"

    def setUp(self):
        self.staff = get_user_model().objects.create_superuser(
            email="orders-admin@example.com",
            phone="01912345678",
            full_name="Orders Admin",
            password=self.password,
        )
        self.customer = get_user_model().objects.create_user(
            email="buyer@example.com",
            phone="01712345678",
            full_name="Buyer Example",
            password=self.password,
        )
        category = Category.objects.create(name="Shirts", slug="shirts")
        product = Product.objects.create(
            category=category,
            name="Oxford Shirt",
            slug="oxford-shirt",
            description="Cotton",
            base_price=Decimal("1290.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=product, size="M", color="BLACK", stock=10, sku="OXF-M-BLACK"
        )
        self.order = self.create_order("EZ-20260924-1001")
        self.client.force_login(self.staff)

    def create_order(self, order_number, status=Order.Status.PENDING):
        order = Order.objects.create(
            order_number=order_number,
            user=self.customer,
            status=status,
            payment_method=Order.PaymentMethod.COD,
            total_amount=Decimal("1290.00"),
            shipping_full_name="Buyer Example",
            shipping_phone="01712345678",
            shipping_address="12 Export Road",
            shipping_area="Meherpur Sadar",
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot="Oxford Shirt",
            size_snapshot="M",
            color_snapshot="BLACK",
            quantity=1,
            price=Decimal("1290.00"),
            subtotal=Decimal("1290.00"),
        )
        return order

    def change_url(self, order=None):
        return reverse("admin:orders_order_change", args=[(order or self.order).pk])

    def change_data(self, **overrides):
        data = {
            "user": self.customer.pk,
            "status": self.order.status,
            "status_note": "",
            "payment_method": Order.PaymentMethod.COD,
            "shipping_full_name": "Buyer Example",
            "shipping_phone": "01712345678",
            "shipping_address": "12 Export Road",
            "shipping_area": "Meherpur Sadar",
            "delivery_note": "",
            "estimated_delivery": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": str(self.order.items.first().pk),
            "items-0-product_variant": str(self.variant.pk),
            "items-0-quantity": "1",
            "status_history-TOTAL_FORMS": "0",
            "status_history-INITIAL_FORMS": "0",
            "status_history-MIN_NUM_FORMS": "0",
            "status_history-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def status_options(self, response):
        select = re.search(r'<select name="status".*?</select>', response.content.decode(), re.S)
        return re.findall(r'<option value="([A-Z_]+)"', select.group(0))

    def run_bulk_action(self, action, orders, **extra):
        payload = {
            "action": action,
            "index": "0",
            "_selected_action": [str(order.pk) for order in orders],
        }
        payload.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("admin:orders_order_changelist"), payload, follow=True)

    def test_dropdown_lists_only_the_valid_next_steps(self):
        response = self.client.get(self.change_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.status_options(response), ["PENDING", "CONFIRMED", "CANCELLED"])

    def test_dropdown_locks_a_closed_order(self):
        self.order.status = Order.Status.DELIVERED
        self.order.save(update_fields=["status"])

        response = self.client.get(self.change_url())

        self.assertEqual(self.status_options(response), ["DELIVERED"])

    def test_change_form_advances_the_status_and_records_history(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.change_url(),
                self.change_data(
                    status=Order.Status.CONFIRMED,
                    status_note="Confirmed by the admin",
                ),
            )

        self.assertRedirects(response, reverse("admin:orders_order_changelist"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        history = self.order.status_history.get()
        self.assertEqual(history.status, Order.Status.CONFIRMED)
        self.assertEqual(history.changed_by, self.staff)
        self.assertEqual(history.note, "Confirmed by the admin")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Order Confirmed", mail.outbox[0].subject)

    def test_change_form_rejects_an_illegal_transition(self):
        response = self.client.post(
            self.change_url(), self.change_data(status=Order.Status.DELIVERED)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(OrderStatusHistory.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_status_note_falls_back_to_a_default_and_stamps_cancellations(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.change_url(), self.change_data(status=Order.Status.CANCELLED))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertIn("Marked as Cancelled", self.order.status_history.get().note)

    def test_bulk_action_marks_orders_confirmed(self):
        response = self.run_bulk_action("mark_confirmed", [self.order])

        self.assertContains(response, "1 order(s) marked as Confirmed")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(self.order.status_history.get().changed_by, self.staff)
        self.assertEqual(len(mail.outbox), 1)

    def test_bulk_action_skips_orders_that_cannot_move(self):
        delivered = self.create_order("EZ-20260924-1002", status=Order.Status.DELIVERED)

        response = self.run_bulk_action("mark_confirmed", [self.order, delivered])

        self.assertContains(response, "1 order(s) marked as Confirmed")
        self.assertContains(response, "Skipped 1 order(s) that cannot move to Confirmed")
        self.assertContains(response, delivered.order_number)
        self.order.refresh_from_db()
        delivered.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(delivered.status, Order.Status.DELIVERED)
        self.assertEqual(len(mail.outbox), 1)

    def test_bulk_action_can_cancel_orders(self):
        response = self.run_bulk_action("mark_cancelled", [self.order])

        self.assertContains(response, "1 order(s) marked as Cancelled")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_cancelling_through_the_admin_returns_units_to_stock(self):
        self.run_bulk_action("mark_cancelled", [self.order])

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 11)  # 10 seeded + 1 ordered unit back
        self.assertIn("1 unit(s) returned to stock", self.order.status_history.get().note)

    def test_confirming_an_order_does_not_touch_stock(self):
        self.run_bulk_action("mark_confirmed", [self.order])

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_order_page_shows_the_read_only_history_inline(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                self.change_url(),
                self.change_data(status=Order.Status.CONFIRMED, status_note="Inline check"),
            )

        response = self.client.get(self.change_url())

        self.assertContains(response, "status_history-")
        self.assertContains(response, "Inline check")

    def test_history_changelist_links_back_to_the_order(self):
        OrderStatusHistory.objects.create(
            order=self.order,
            status=Order.Status.PENDING,
            changed_by=self.staff,
            note="Order placed",
        )

        response = self.client.get(reverse("admin:orders_orderstatushistory_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.change_url())
