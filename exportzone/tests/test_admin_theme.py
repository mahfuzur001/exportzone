"""Admin theme audit: django-jazzmin is installed, branded like the storefront, and renders."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class JazzminConfigurationTests(SimpleTestCase):
    """The admin skin must stay wired to the EXPORT ZONE branding."""

    def test_jazzmin_loads_before_the_django_admin(self):
        installed = list(settings.INSTALLED_APPS)

        self.assertIn("jazzmin", installed)
        self.assertLess(
            installed.index("jazzmin"), installed.index("django.contrib.admin")
        )

    def test_branding_settings_match_the_storefront(self):
        brand = settings.JAZZMIN_SETTINGS

        self.assertEqual(brand["site_header"], "EXPORT ZONE")
        self.assertEqual(brand["site_brand"], "EXPORT ZONE")
        self.assertEqual(brand["custom_css"], "css/admin_brand.css")
        self.assertEqual(brand["site_logo"], "img/brand-mark.svg")
        self.assertTrue(brand["show_sidebar"])
        self.assertIn("EXPORT ZONE", brand["copyright"])

    def test_theme_is_a_real_bootswatch_theme_in_dark_mode(self):
        tweaks = settings.JAZZMIN_UI_TWEAKS

        self.assertEqual(tweaks["theme"], "darkly")
        self.assertEqual(tweaks["default_theme_mode"], "dark")
        self.assertIsNotNone(
            finders.find(f"vendor/bootswatch/{tweaks['theme']}/bootstrap.min.css")
        )

    def test_brand_assets_are_served_by_the_static_finders(self):
        brand = settings.JAZZMIN_SETTINGS

        for path in (brand["custom_css"], brand["site_logo"], brand["site_icon"], brand["login_logo"]):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path), f"{path} is missing")

    def test_side_menu_icons_and_search_cover_the_store_apps(self):
        brand = settings.JAZZMIN_SETTINGS

        for key in (
            "store.Product",
            "store.Category",
            "store.ProductVariant",
            "orders.Order",
            "accounts.CustomUser",
            "cart.Cart",
        ):
            with self.subTest(key=key):
                self.assertIn(key, brand["icons"])

        self.assertIn("store.Product", brand["search_model"])
        self.assertEqual(brand["order_with_respect_to"][0], "store")


class AdminThemeRenderingTests(TestCase):
    """Rendered admin pages carry the jazzmin shell and the storefront palette."""

    password = "A-strong-passphrase-42"

    def setUp(self):
        self.staff = get_user_model().objects.create_superuser(
            email="theme-admin@example.com",
            phone="01912345678",
            full_name="Theme Admin",
            password=self.password,
        )

    def test_login_page_is_branded(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "jazzmin/css/main.css")
        self.assertContains(response, "css/admin_brand.css")
        self.assertContains(response, "control room")
        self.assertContains(response, "brand-lockup.svg")

    def test_dashboard_renders_the_jazzmin_shell(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app-sidebar")
        self.assertContains(response, "brand-mark.svg")
        self.assertContains(response, "fa-tshirt")

    def test_store_changelists_render_for_staff(self):
        self.client.force_login(self.staff)

        for name in (
            "admin:store_product_changelist",
            "admin:store_category_changelist",
            "admin:orders_order_changelist",
            "admin:accounts_customuser_changelist",
            "admin:cart_cart_changelist",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_admin_requires_a_staff_account(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])
