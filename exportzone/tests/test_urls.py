"""URL audit: every spec route reverses to the expected path (spec sections 42-43)."""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import Resolver404, resolve, reverse


class SpecUrlResolutionTests(SimpleTestCase):
    def test_public_storefront_routes(self):
        self.assertEqual(reverse("store:home"), "/")
        self.assertEqual(reverse("store:shop"), "/shop/")
        self.assertEqual(
            reverse("store:product_detail", kwargs={"slug": "classic-slim-jeans"}),
            "/product/classic-slim-jeans/",
        )
        self.assertEqual(reverse("store:about"), "/about/")
        self.assertEqual(reverse("store:contact"), "/contact/")

    def test_cart_and_checkout_routes(self):
        self.assertEqual(reverse("cart:detail"), "/cart/")
        self.assertEqual(reverse("cart:add"), "/cart/add/")
        self.assertEqual(reverse("cart:clear"), "/cart/clear/")
        self.assertEqual(reverse("orders:checkout"), "/checkout/")
        self.assertEqual(
            reverse(
                "orders:confirmation", kwargs={"order_number": "EZ-20260101-ABCD"}
            ),
            "/order-success/EZ-20260101-ABCD/",
        )

    def test_order_routes(self):
        self.assertEqual(reverse("orders:list"), "/account/orders/")
        self.assertEqual(
            reverse("orders:detail", kwargs={"order_number": "EZ-20260101-ABCD"}),
            "/account/orders/EZ-20260101-ABCD/",
        )
        self.assertEqual(
            reverse("orders:cancel", kwargs={"order_number": "EZ-20260101-ABCD"}),
            "/account/orders/EZ-20260101-ABCD/cancel/",
        )

    def test_authentication_routes(self):
        self.assertEqual(reverse("accounts:register"), "/register/")
        self.assertEqual(reverse("accounts:login"), "/login/")
        self.assertEqual(reverse("accounts:logout"), "/logout/")
        self.assertEqual(reverse("accounts:password_reset"), "/forgot-password/")
        self.assertEqual(
            reverse("accounts:password_reset_done"), "/forgot-password/done/"
        )
        self.assertEqual(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": "uid", "token": "tok"},
            ),
            "/reset-password/uid/tok/",
        )
        self.assertEqual(
            reverse("accounts:password_reset_complete"),
            "/reset-password/complete/",
        )

    def test_account_self_service_routes(self):
        self.assertEqual(reverse("accounts:account"), "/account/")
        self.assertEqual(reverse("accounts:address_list"), "/account/addresses/")
        self.assertEqual(reverse("accounts:address_add"), "/account/addresses/add/")
        self.assertEqual(
            reverse("accounts:address_edit", kwargs={"address_id": 5}),
            "/account/addresses/5/edit/",
        )
        self.assertEqual(
            reverse("accounts:address_delete", kwargs={"address_id": 5}),
            "/account/addresses/5/delete/",
        )
        self.assertEqual(
            reverse("accounts:address_set_default", kwargs={"address_id": 5}),
            "/account/addresses/5/default/",
        )
        self.assertEqual(reverse("accounts:change_password"), "/account/password/")

    def test_admin_dashboard_route(self):
        self.assertEqual(reverse("admin_dashboard:dashboard"), "/admin-dashboard/")

    def test_removed_email_verification_routes_no_longer_resolve(self):
        for removed in (
            "/verify-email/sent/",
            "/verify-email/success/",
            "/verify-email/MQ/token/",
        ):
            with self.subTest(path=removed):
                with self.assertRaises(Resolver404):
                    resolve(removed)

    def test_legacy_prefixed_account_urls_no_longer_resolve(self):
        for legacy in ("/accounts/login/", "/accounts/register/", "/accounts/"):
            with self.assertRaises(Resolver404):
                resolve(legacy)


class SpecPageResponseTests(TestCase):
    def test_public_pages_respond_with_200(self):
        for path in (
            "/",
            "/shop/",
            "/about/",
            "/contact/",
            "/register/",
            "/login/",
            "/forgot-password/",
            "/reset-password/complete/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_account_pages_require_login_and_then_respond(self):
        for path in (
            "/account/",
            "/account/addresses/",
            "/account/addresses/add/",
            "/account/password/",
            "/account/orders/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn(f"{reverse('accounts:login')}?next={path}", response["Location"])

        user = get_user_model().objects.create_user(
            email="urlaudit@example.com",
            phone="01700000000",
            full_name="URL Audit",
            password="A-strong-passphrase-42",
        )
        self.client.force_login(user)
        for path in (
            "/account/",
            "/account/addresses/",
            "/account/addresses/add/",
            "/account/password/",
            "/account/orders/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)