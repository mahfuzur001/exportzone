from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Address
from apps.cart.models import Cart, CartItem
from apps.store.models import Category, Product, ProductVariant

from .models import Order, OrderItem
from .services import create_order_from_cart


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OrderFlowTests(TestCase):
    password = "A-strong-passphrase-42"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="buyer@example.com", phone="01712345678", full_name="Buyer Example", password=self.password
        )
        self.other_user = get_user_model().objects.create_user(
            email="other-buyer@example.com", phone="01812345678", full_name="Other Buyer", password=self.password
        )
        category = Category.objects.create(name="Jeans", slug="jeans")
        self.product = Product.objects.create(
            category=category, name="Premium Jeans", slug="premium-jeans", description="Denim", base_price=Decimal("2499.00")
        )
        self.variant = ProductVariant.objects.create(product=self.product, size="32", color="BLUE", stock=5, sku="JEANS-32-BLUE")
        self.client.force_login(self.user)

    def add_to_cart(self, quantity=2):
        CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=quantity)

    def checkout_data(self, **overrides):
        data = {
            "full_name": "Buyer Example",
            "phone": "01712345678",
            "address": "12 Export Road",
            "area": "Meherpur Sadar",
            "delivery_note": "Call before delivery",
            "payment_method": "COD",
            "delivery_option": "HOME_DELIVERY",
        }
        data.update(overrides)
        return data

    def test_anonymous_checkout_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("orders:checkout"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('orders:checkout')}")

    def test_empty_cart_redirects_from_checkout(self):
        response = self.client.get(reverse("orders:checkout"))
        self.assertRedirects(response, reverse("cart:detail"))

    def test_checkout_page_loads_with_cod(self):
        self.add_to_cart()
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cash on Delivery")
        self.assertContains(response, "4998.00")

    def test_invalid_phone_and_missing_address_are_rejected(self):
        self.add_to_cart()
        response = self.client.post(reverse("orders:checkout"), self.checkout_data(phone="123", address=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid Bangladesh phone number")
        self.assertFalse(Order.objects.exists())

    def test_non_cod_payment_is_rejected(self):
        self.add_to_cart()
        response = self.client.post(reverse("orders:checkout"), self.checkout_data(payment_method="BKASH"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Order.objects.exists())

    def test_successful_order_calculates_total_reduces_stock_and_clears_cart(self):
        self.add_to_cart(2)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        self.assertRedirects(response, reverse("orders:confirmation", kwargs={"order_number": order.order_number}))
        self.assertRegex(order.order_number, r"^EZ-\d{8}-\d{4}$")
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total_amount, Decimal("4998.00"))
        self.assertEqual(order.shipping_charge, Decimal("0.00"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())
        self.assertEqual(OrderItem.objects.get().price, Decimal("2499.00"))
        self.assertEqual(len(mail.outbox), 1)

    def test_order_item_price_is_snapshot(self):
        self.add_to_cart()
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        item = OrderItem.objects.get()
        self.product.base_price = Decimal("3999.00")
        self.product.save()
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("2499.00"))
        self.assertEqual(item.subtotal, Decimal("4998.00"))

    def test_insufficient_stock_rolls_back_order_and_cart(self):
        self.add_to_cart(6)
        response = self.client.post(reverse("orders:checkout"), self.checkout_data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insufficient stock")
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.get().quantity, 6)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_inactive_product_prevents_order(self):
        self.add_to_cart()
        self.product.is_active = False
        self.product.save()
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CartItem.objects.filter(cart__user=self.user).exists())

    @patch("apps.orders.services.send_order_confirmation_email", side_effect=RuntimeError("mail down"))
    def test_email_failure_does_not_rollback_order(self, mocked_email):
        self.add_to_cart()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("orders:checkout"), self.checkout_data())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Order.objects.exists())
        mocked_email.assert_called_once()

    def test_confirmation_and_order_history_are_owner_scoped(self):
        self.add_to_cart()
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        self.assertEqual(self.client.get(reverse("orders:confirmation", kwargs={"order_number": order.order_number})).status_code, 200)
        self.assertEqual(self.client.get(reverse("orders:list")).status_code, 200)
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(reverse("orders:detail", kwargs={"order_number": order.order_number})).status_code, 404)
        self.assertEqual(self.client.get(reverse("orders:confirmation", kwargs={"order_number": order.order_number})).status_code, 404)

    def test_status_transitions_are_restricted(self):
        self.add_to_cart()
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        order.set_status(Order.Status.CONFIRMED)
        order.set_status(Order.Status.PROCESSING)
        order.set_status(Order.Status.SHIPPED)
        order.set_status(Order.Status.DELIVERED)
        self.assertEqual(order.status, Order.Status.DELIVERED)
        with self.assertRaises(ValidationError):
            order.set_status(Order.Status.PROCESSING)

    def test_cancel_is_post_only(self):
        self.add_to_cart()
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        self.assertEqual(self.client.get(reverse("orders:cancel", kwargs={"order_number": order.order_number})).status_code, 405)
        response = self.client.post(reverse("orders:cancel", kwargs={"order_number": order.order_number}))
        self.assertRedirects(response, reverse("orders:detail", kwargs={"order_number": order.order_number}))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_customer_cancellation_returns_units_to_stock(self):
        self.add_to_cart(quantity=2)
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)  # 5 seeded - 2 bought

        self.client.post(reverse("orders:cancel", kwargs={"order_number": order.order_number}))

        self.variant.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(self.variant.stock, 5)  # the 2 units are back
        cancellation = order.status_history.filter(status=Order.Status.CANCELLED).get()
        self.assertIn("2 unit(s) returned to stock", cancellation.note)

    def test_repeated_cancellation_does_not_credit_stock_twice(self):
        self.add_to_cart(quantity=2)
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        url = reverse("orders:cancel", kwargs={"order_number": order.order_number})

        self.client.post(url)
        self.client.post(url)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)  # still 5, not 7

    def test_cannot_cancel_a_shipped_order(self):
        self.add_to_cart()
        self.client.post(reverse("orders:checkout"), self.checkout_data())
        order = Order.objects.get()
        order.set_status(Order.Status.CONFIRMED)
        order.set_status(Order.Status.PROCESSING)
        order.set_status(Order.Status.SHIPPED)
        order.save(update_fields=["status"])

        self.client.post(reverse("orders:cancel", kwargs={"order_number": order.order_number}))

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(self.variant.stock, 3)  # 5 seeded - 2 bought, nothing came back

    def test_checkout_renders_saved_address_picker_and_prefills_from_default(self):
        default_address = Address.objects.create(
            user=self.user,
            is_default=True,
            full_name="Buyer Example",
            phone="01712345678",
            address="45 Warehouse Lane",
            area="Meherpur Sadar",
        )
        Address.objects.create(
            user=self.user,
            full_name="Buyer Example",
            phone="01712345678",
            address="99 Hill View",
            area="Khulna",
        )
        self.add_to_cart()

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saved addresses")
        self.assertContains(response, "data-address-json")
        self.assertContains(response, "45 Warehouse Lane")
        self.assertContains(response, "99 Hill View")
        self.assertContains(response, default_address.full_name)

        # The picker's extra field must not interfere with order creation.
        response = self.client.post(
            reverse("orders:checkout"),
            self.checkout_data(saved_address=default_address.pk),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Order.objects.exists())
