from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.store.models import Category, Product, ProductVariant


class AdminDashboardTests(TestCase):
    password = "A-strong-passphrase-42"

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            phone="01712345678",
            full_name="Admin",
            password=self.password,
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            phone="01812345678",
            full_name="Staff",
            password=self.password,
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            phone="01912345678",
            full_name="Customer",
            password=self.password,
        )
        self.category = Category.objects.create(name="Jeans", slug="jeans")
        self.product = Product.objects.create(
            category=self.category,
            name="Admin Jeans",
            slug="admin-jeans",
            description="Denim",
            base_price=Decimal("100.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="32",
            color="BLUE",
            stock=2,
            sku="ADMIN-32-BLUE",
        )
        self.client.force_login(self.admin)

    def create_order(self, user=None, status=Order.Status.PENDING, total=Decimal("100.00")):
        order = Order.objects.create(
            order_number=f"EZ-20260923-{Order.objects.count() + 1:04d}",
            user=user or self.customer,
            status=status,
            payment_method="COD",
            total_amount=total,
            shipping_full_name="Customer",
            shipping_phone="01912345678",
            shipping_address="Road 1",
            shipping_area="Meherpur",
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            size_snapshot="32",
            color_snapshot="BLUE",
            quantity=1,
            price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
        )
        return order

    def test_anonymous_and_customer_access_are_protected(self):
        self.client.logout()
        response = self.client.get(reverse("admin_dashboard:dashboard"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('admin_dashboard:dashboard')}")
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("admin_dashboard:dashboard")).status_code, 403)

    def test_staff_and_superuser_can_access_dashboard(self):
        self.assertEqual(self.client.get(reverse("admin_dashboard:dashboard")).status_code, 200)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin_dashboard:dashboard")).status_code, 200)

    def test_dashboard_statistics_are_database_driven(self):
        self.create_order(total=Decimal("100.00"))
        self.create_order(status=Order.Status.CANCELLED, total=Decimal("900.00"))
        response = self.client.get(reverse("admin_dashboard:dashboard"))
        self.assertEqual(response.context["stats"]["total_orders"], 2)
        self.assertEqual(response.context["stats"]["total_revenue"], Decimal("100.00"))
        self.assertEqual(response.context["stats"]["low_stock_products"], 1)

    def test_order_search_filter_detail_and_valid_status_history(self):
        order = self.create_order()
        self.assertContains(
            self.client.get(reverse("admin_dashboard:orders"), {"q": order.order_number}),
            order.order_number,
        )
        self.assertContains(
            self.client.get(reverse("admin_dashboard:orders"), {"status": "PENDING"}),
            order.order_number,
        )
        detail = self.client.get(reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}))
        self.assertEqual(detail.status_code, 200)
        response = self.client.post(
            reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
            {"status": "CONFIRMED", "note": "Packed"},
        )
        self.assertRedirects(response, reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertTrue(OrderStatusHistory.objects.filter(order=order, status="CONFIRMED", changed_by=self.admin).exists())

    def test_invalid_status_transition_is_rejected(self):
        order = self.create_order(status=Order.Status.DELIVERED)
        response = self.client.post(
            reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
            {"status": "PROCESSING"},
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    @patch("apps.admin_dashboard.services.send_order_status_update_email", return_value=True)
    def test_status_update_sends_email_when_configured(self, mock_send):
        order = self.create_order()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
                {"status": "CONFIRMED"},
            )
        mock_send.assert_called_once()

    @patch("apps.admin_dashboard.services.send_order_status_update_email", side_effect=RuntimeError("mail down"))
    def test_email_failure_does_not_break_status_update(self, _mock_send):
        order = self.create_order()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
                {"status": "CONFIRMED"},
            )
        self.assertRedirects(response, reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_product_create_edit_and_safe_deactivation(self):
        response = self.client.post(
            reverse("admin_dashboard:product_add"),
            {
                "category": self.category.pk,
                "name": "New Admin Product",
                "slug": "new-admin-product",
                "description": "Description",
                "base_price": "55.00",
                "is_active": "on",
                "featured": "on",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-size": "M",
                "variants-0-color": "BLACK",
                "variants-0-stock": "4",
                "variants-0-sku": "NEW-M-BLACK",
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Product.objects.get(slug="new-admin-product")
        self.assertTrue(ProductVariant.objects.filter(product=created, sku="NEW-M-BLACK").exists())
        self.client.post(reverse("admin_dashboard:product_delete", kwargs={"product_id": self.product.pk}))
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_categories_customers_and_low_stock_pages(self):
        self.assertEqual(self.client.get(reverse("admin_dashboard:categories")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_dashboard:customers")).status_code, 200)
        response = self.client.get(reverse("admin_dashboard:low_stock"))
        self.assertContains(response, self.variant.sku)
        detail = self.client.get(reverse("admin_dashboard:customer_detail", kwargs={"user_id": self.customer.pk}))
        self.assertNotContains(detail, self.password)
        self.assertNotContains(detail, "password")

    def test_admin_cancellation_returns_units_to_stock(self):
        order = self.create_order()
        self.assertEqual(self.variant.stock, 2)

        self.client.post(
            reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
            {"status": Order.Status.CANCELLED, "note": "Customer called to cancel."},
        )

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.variant.stock, 3)  # the single ordered unit came back
        self.assertIn("Customer called to cancel.", order.status_history.get().note)
        self.assertIn("1 unit(s) returned to stock", order.status_history.get().note)

    def test_admin_cancelling_twice_does_not_double_credit(self):
        order = self.create_order()
        url = reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number})

        self.client.post(url, {"status": Order.Status.CANCELLED, "note": ""})
        self.client.post(url, {"status": Order.Status.CANCELLED, "note": ""})

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)  # not 4

    def test_dashboard_reports_total_units_in_stock(self):
        ProductVariant.objects.create(
            product=self.product, size="34", color="BLACK", stock=7, sku="ADMIN-34-BLACK"
        )
        response = self.client.get(reverse("admin_dashboard:dashboard"))

        stats = response.context["stats"]
        self.assertEqual(stats["total_stock_units"], 9)  # 2 + 7
        self.assertEqual(stats["out_of_stock_variants"], 0)
        self.assertContains(response, "Units in stock")

    def test_product_list_shows_units_in_stock(self):
        ProductVariant.objects.create(
            product=self.product, size="34", color="BLACK", stock=7, sku="ADMIN-34-BLACK"
        )
        response = self.client.get(reverse("admin_dashboard:products"))

        self.assertContains(response, "In stock")
        product = response.context["products"][0]
        self.assertEqual(product.variant_count, 2)
        self.assertEqual(product.total_stock, 9)  # 2 + 7, not multiplied by the join

    def test_customer_can_be_toggled_active(self):
        self.client.post(reverse("admin_dashboard:customer_toggle_active", kwargs={"user_id": self.customer.pk}))
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_category_delete_only_when_empty(self):
        empty = Category.objects.create(name="Empty", slug="empty-cat")
        self.client.post(reverse("admin_dashboard:category_delete", kwargs={"category_id": empty.pk}))
        self.assertFalse(Category.objects.filter(pk=empty.pk).exists())
        self.client.post(reverse("admin_dashboard:category_delete", kwargs={"category_id": self.category.pk}))
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_dashboard_mutation_requires_post(self):
        order = self.create_order()
        response = self.client.get(reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_dashboard:product_delete", kwargs={"product_id": self.product.pk})).status_code, 405)

    def test_csrf_protects_status_update(self):
        order = self.create_order()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(
            reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
            {"status": "CONFIRMED"},
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_post_from_customer_is_rejected(self):
        order = self.create_order()
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("admin_dashboard:order_detail", kwargs={"order_number": order.order_number}),
            {"status": "CONFIRMED"},
        )
        self.assertEqual(response.status_code, 403)

    def test_pagination_preserves_filters(self):
        for index in range(25):
            self.create_order(total=Decimal("10.00") + index)
        response = self.client.get(reverse("admin_dashboard:orders"), {"status": "PENDING", "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "page=1")
        self.assertContains(response, "status=PENDING")
