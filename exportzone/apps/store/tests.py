from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, ContactMessage, Product, ProductVariant


class StoreModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Jeans", slug="jeans")

    def test_category_creation(self):
        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(self.category.slug, "jeans")

    def test_category_slug_uniqueness(self):
        with self.assertRaises(Exception):
            Category.objects.create(name="Jeans", slug="jeans")

    def test_active_category_appears_publicly(self):
        response = self.client.get(reverse("store:shop"))
        self.assertContains(response, "Jeans")

    def test_inactive_category_hidden_publicly(self):
        self.category.is_active = False
        self.category.save()
        response = self.client.get(reverse("store:shop"))
        self.assertNotContains(response, "Jeans")

    def test_product_creation(self):
        product = Product.objects.create(
            category=self.category,
            name="Premium Denim Jeans",
            slug="premium-denim-jeans",
            description="A premium denim staple.",
            base_price=Decimal("69.99"),
        )
        self.assertEqual(product.name, "Premium Denim Jeans")

    def test_product_slug_uniqueness(self):
        Product.objects.create(
            category=self.category,
            name="Premium Denim Jeans",
            slug="premium-denim-jeans",
            description="A premium denim staple.",
            base_price=Decimal("69.99"),
        )
        with self.assertRaises(Exception):
            Product.objects.create(
                category=self.category,
                name="Duplicate Slug",
                slug="premium-denim-jeans",
                description="Dup.",
                base_price=Decimal("79.99"),
            )

    def test_negative_price_rejected(self):
        product = Product(category=self.category, name="Bad Price", slug="bad-price", description="Bad", base_price=Decimal("-1.00"))
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_inactive_product_hidden(self):
        Product.objects.create(
            category=self.category,
            name="Hidden Product",
            slug="hidden-product",
            description="Do not show.",
            base_price=Decimal("29.99"),
            is_active=False,
        )
        response = self.client.get(reverse("store:shop"))
        self.assertNotContains(response, "Hidden Product")

    def test_variant_creation(self):
        product = Product.objects.create(
            category=self.category,
            name="Variant Product",
            slug="variant-product",
            description="Variant test.",
            base_price=Decimal("99.99"),
        )
        variant = ProductVariant.objects.create(
            product=product,
            size="32",
            color="BLUE",
            stock=12,
            sku="EZ-TEST-32-BLUE",
        )
        self.assertEqual(variant.stock, 12)

    def test_sku_uniqueness(self):
        product = Product.objects.create(
            category=self.category,
            name="Variant Product A",
            slug="variant-product-a",
            description="SKU test.",
            base_price=Decimal("99.99"),
        )
        ProductVariant.objects.create(product=product, size="32", color="BLUE", stock=5, sku="UNIQUE-SKU")
        with self.assertRaises(Exception):
            ProductVariant.objects.create(product=product, size="34", color="BLACK", stock=5, sku="UNIQUE-SKU")

    def test_negative_stock_rejected(self):
        product = Product.objects.create(
            category=self.category,
            name="Variant Product B",
            slug="variant-product-b",
            description="Stock test.",
            base_price=Decimal("40.00"),
        )
        variant = ProductVariant(product=product, size="M", color="WHITE", stock=-1, sku="NEGATIVE-STOCK")
        with self.assertRaises(ValidationError):
            variant.full_clean()

    def test_duplicate_product_size_color_rejected(self):
        product = Product.objects.create(
            category=self.category,
            name="Variant Product C",
            slug="variant-product-c",
            description="Duplicate test.",
            base_price=Decimal("45.00"),
        )
        ProductVariant.objects.create(product=product, size="32", color="BLUE", stock=7, sku="DUP-1")
        with self.assertRaises(Exception):
            ProductVariant.objects.create(product=product, size="32", color="BLUE", stock=9, sku="DUP-2")

    def test_multiple_images_supported(self):
        product = Product.objects.create(
            category=self.category,
            name="Image Product",
            slug="image-product",
            description="Image test.",
            base_price=Decimal("85.00"),
        )
        product.images.create(image="products/test1.jpg", alt_text="Front")
        product.images.create(image="products/test2.jpg", alt_text="Back")
        self.assertEqual(product.images.count(), 2)

    def test_shop_page_returns_200(self):
        response = self.client.get(reverse("store:shop"))
        self.assertEqual(response.status_code, 200)

    def test_only_active_products_displayed(self):
        Product.objects.create(
            category=self.category,
            name="Visible Product",
            slug="visible-product",
            description="Visible.",
            base_price=Decimal("99.00"),
        )
        Product.objects.create(
            category=self.category,
            name="Hidden Product 2",
            slug="hidden-product-2",
            description="Hidden.",
            base_price=Decimal("88.00"),
            is_active=False,
        )
        response = self.client.get(reverse("store:shop"))
        self.assertContains(response, "Visible Product")
        self.assertNotContains(response, "Hidden Product 2")

    def test_category_filter_works(self):
        category_b = Category.objects.create(name="Shirts", slug="shirts")
        Product.objects.create(category=self.category, name="Jeans Product", slug="jeans-product", description="Jeans", base_price=Decimal("49.00"))
        Product.objects.create(category=category_b, name="Shirt Product", slug="shirt-product", description="Shirt", base_price=Decimal("39.00"))
        response = self.client.get(reverse("store:shop"), {"category": "jeans"})
        self.assertContains(response, "Jeans Product")
        self.assertNotContains(response, "Shirt Product")

    def test_size_filter_works(self):
        product = Product.objects.create(category=self.category, name="Sized Product", slug="sized-product", description="Sizing", base_price=Decimal("59.00"))
        ProductVariant.objects.create(product=product, size="32", color="BLUE", stock=5, sku="SIZE-32")
        response = self.client.get(reverse("store:shop"), {"size": "32"})
        self.assertContains(response, "Sized Product")

    def test_color_filter_works(self):
        product = Product.objects.create(category=self.category, name="Color Product", slug="color-product", description="Coloring", base_price=Decimal("59.00"))
        ProductVariant.objects.create(product=product, size="32", color="BLUE", stock=5, sku="COLOR-32")
        response = self.client.get(reverse("store:shop"), {"color": "BLUE"})
        self.assertContains(response, "Color Product")

    def test_price_filter_works(self):
        Product.objects.create(category=self.category, name="Cheap Product", slug="cheap-product", description="Cheap", base_price=Decimal("15.00"))
        Product.objects.create(category=self.category, name="Expensive Product", slug="expensive-product", description="Expensive", base_price=Decimal("150.00"))
        response = self.client.get(reverse("store:shop"), {"min_price": "20", "max_price": "100"})
        self.assertContains(response, "Price")

    def test_search_works(self):
        Product.objects.create(category=self.category, name="Denim Classic", slug="denim-classic", description="Classic denim", base_price=Decimal("79.00"))
        response = self.client.get(reverse("store:shop"), {"q": "classic"})
        self.assertContains(response, "Denim Classic")

    def test_sorting_works(self):
        Product.objects.create(category=self.category, name="A Product", slug="a-product", description="A", base_price=Decimal("40.00"))
        Product.objects.create(category=self.category, name="B Product", slug="b-product", description="B", base_price=Decimal("60.00"))
        response = self.client.get(reverse("store:shop"), {"sort": "price_low"})
        self.assertEqual(response.status_code, 200)

    def test_pagination_works(self):
        for index in range(15):
            Product.objects.create(category=self.category, name=f"P{index}", slug=f"p-{index}", description="Page test", base_price=Decimal("20.00"))
        response = self.client.get(reverse("store:shop"), {"page": "2"})
        self.assertEqual(response.status_code, 200)

    def test_product_detail_returns_200(self):
        product = Product.objects.create(category=self.category, name="Detail Product", slug="detail-product", description="Detail view", base_price=Decimal("89.00"))
        response = self.client.get(reverse("store:product_detail", kwargs={"slug": product.slug}))
        self.assertEqual(response.status_code, 200)

    def test_invalid_slug_returns_404(self):
        response = self.client.get(reverse("store:product_detail", kwargs={"slug": "unknown-slug"}))
        self.assertEqual(response.status_code, 404)

    def test_variant_information_displayed(self):
        product = Product.objects.create(category=self.category, name="Variant Display", slug="variant-display", description="Display", base_price=Decimal("55.00"))
        ProductVariant.objects.create(product=product, size="32", color="BLUE", stock=10, sku="DISPLAY-32-BLUE")
        response = self.client.get(reverse("store:product_detail", kwargs={"slug": product.slug}))
        self.assertContains(response, "32")
        self.assertContains(response, "BLUE")


class ContactFormTests(TestCase):
    def test_contact_page_renders_form(self):
        response = self.client.get(reverse("store:contact"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Message")
        self.assertContains(response, "Phone (optional)")

    def test_valid_contact_message_is_stored(self):
        response = self.client.post(
            reverse("store:contact"),
            {
                "name": "Rafi Hasan",
                "email": "rafi@example.com",
                "phone": "01712345678",
                "message": "Please share sizing guidance for the slim jeans.",
            },
        )

        self.assertRedirects(response, reverse("store:contact"))
        message = ContactMessage.objects.get()
        self.assertEqual(message.name, "Rafi Hasan")
        self.assertEqual(message.email, "rafi@example.com")
        self.assertEqual(message.phone, "01712345678")

    def test_contact_form_is_validated_and_stores_nothing_on_error(self):
        response = self.client.post(
            reverse("store:contact"),
            {
                "name": "R",
                "email": "not-an-email",
                "phone": "123",
                "message": "hi",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "Enter a valid email address.")
        self.assertContains(response, "Tell us a little more")

    def test_contact_phone_is_optional(self):
        response = self.client.post(
            reverse("store:contact"),
            {
                "name": "Suma Akter",
                "email": "suma@example.com",
                "message": "Do you deliver to Khulna district?",
            },
        )

        self.assertRedirects(response, reverse("store:contact"))
        self.assertEqual(ContactMessage.objects.get().phone, "")


class SeedDataTests(TestCase):
    def test_seed_data_creates_spec_catalog_and_is_idempotent(self):
        from django.core.management import call_command

        call_command("seed_data")
        category_count = Category.objects.count()
        product_count = Product.objects.count()
        variant_count = ProductVariant.objects.count()
        call_command("seed_data")

        self.assertEqual(Category.objects.count(), category_count)
        self.assertEqual(Product.objects.count(), product_count)
        self.assertEqual(ProductVariant.objects.count(), variant_count)

        expected_categories = {
            "Jeans",
            "Shirts",
            "Polo T-Shirts",
            "T-Shirts",
            "Chinos",
            "Jackets",
            "Accessories",
        }
        self.assertTrue(
            expected_categories.issubset(
                set(Category.objects.values_list("name", flat=True))
            )
        )

        sizes = set(ProductVariant.objects.values_list("size", flat=True))
        for size in ("28", "30", "32", "34", "36", "38", "40", "42"):
            self.assertIn(size, sizes)
        for size in ("S", "M", "L", "XL", "XXL"):
            self.assertIn(size, sizes)

        colors = set(ProductVariant.objects.values_list("color", flat=True))
        self.assertTrue(
            {"BLACK", "BLUE", "NAVY", "WHITE", "GRAY", "BEIGE", "GREEN"}.issubset(colors)
        )
        self.assertTrue(Product.objects.filter(featured=True).exists())

    def test_seeded_products_render_in_shop(self):
        from django.core.management import call_command

        call_command("seed_data")
        response = self.client.get(reverse("store:shop"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Classic Slim Jeans")
        response = self.client.get(reverse("store:home"))
        self.assertEqual(response.status_code, 200)


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class ErrorPageTests(TestCase):
    def test_missing_page_renders_custom_404_template(self):
        response = self.client.get("/product/does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)

    def test_unknown_route_renders_custom_404_template(self):
        response = self.client.get("/definitely-not-a-route/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)

    def test_403_and_500_templates_render(self):
        from django.test import RequestFactory
        from django.views import defaults

        request = RequestFactory().get("/")

        forbidden = defaults.permission_denied(request, exception=None)
        self.assertEqual(forbidden.status_code, 403)
        self.assertIn(b"Access denied", forbidden.content)

        server_error = defaults.server_error(request)
        self.assertEqual(server_error.status_code, 500)
        self.assertIn(b"Something went wrong", server_error.content)
