"""Tests for the on-page SEO layer in :mod:`apps.core.seo`.

These cover what a crawler actually depends on: that a public page emits a unique
title, a description, a self-referencing canonical, an indexable robots directive
and valid JSON-LD, and that private or duplicate URLs do not.

They also pin the two rules that are easy to break by accident later: a private page
must never be indexable, and structured data must never claim a rating the site does
not actually have.
"""

import json
import re
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.orders.models import Order, OrderItem
from apps.store.models import Category, Product, ProductReview, ProductVariant

from . import seo

SITE = "https://www.exportzone.test"


# --- Small parsing helpers, kept here so the assertions below stay readable. ---

def title_of(html):
    match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    return match.group(1).strip() if match else ""


def meta_content(html, kind, value):
    """Content of the first ``<meta>`` whose ``name=`` or ``property=`` is ``value``."""
    pattern = r'<meta\s+%s="%s"\s+content="([^"]*)"' % (re.escape(kind), re.escape(value))
    match = re.search(pattern, html)
    return match.group(1) if match else None


def canonical_of(html):
    match = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return match.group(1) if match else ""


def json_ld_blocks(html):
    """Parse every ``application/ld+json`` block on the page."""
    return [
        json.loads(block)
        for block in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
    ]


def node_of_type(html, type_name):
    return [n for n in json_ld_blocks(html) if n.get("@type") == type_name]


class SeoCatalogMixin:
    """Builds the smallest catalogue that renders a real product page."""

    def setUp(self):
        self.category = Category.objects.create(name="Jeans", slug="jeans")
        self.product = Product.objects.create(
            category=self.category,
            name="Premium Denim Jeans",
            slug="premium-denim-jeans",
            description="A premium denim staple cut for everyday wear.",
            base_price=Decimal("2499.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="32",
            color="NAVY",
            stock=5,
            sku="EZ-JEANS-32-NAVY",
        )
        super().setUp()

    # -- helpers ----------------------------------------------------------
    def product_page(self):
        return self.get(reverse("store:product_detail", kwargs={"slug": self.product.slug}))

    def product_node(self, html):
        return node_of_type(html, "Product")[0]

    def add_review(self, *, rating=5, approved=True):
        """Attach a review through a real order, which the model requires."""
        sequence = CustomUser.objects.count()
        user = CustomUser.objects.create_user(
            email="reviewer%s@example.com" % sequence,
            phone="017%08d" % sequence,
            full_name="Reviewer %s" % sequence,
            password="Str0ngPass!2345",
        )
        order = Order.objects.create(
            order_number="EZ-20260101-%04d" % Order.objects.count(),
            payment_method=Order.PaymentMethod.COD,
            total_amount=Decimal("2499.00"),
            shipping_full_name="Reviewer",
            shipping_phone="01700000000",
            shipping_address="Test address",
            shipping_area="Meherpur",
            user=user,
        )
        item = OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            quantity=1,
            price=self.product.base_price,
            subtotal=self.product.base_price,
        )
        return ProductReview.objects.create(
            product=self.product,
            user=user,
            order=order,
            order_item=item,
            rating=rating,
            title="Great fit",
            comment="Wore it for a week and it still looks new.",
            is_approved=approved,
        )


@override_settings(SITE_URL=SITE)
class SeoHelperTests(TestCase):
    """Unit tests for the pure helpers, with no HTTP involved."""

    def test_title_appends_the_brand_once(self):
        self.assertEqual(seo.build_title("Contact Us"), "Contact Us | Export Zone")

    def test_title_is_not_stuffed_when_the_brand_is_already_present(self):
        self.assertEqual(
            seo.build_title("Contact Us | Export Zone"), "Contact Us | Export Zone"
        )

    def test_empty_title_falls_back_to_the_brand_and_tagline(self):
        self.assertEqual(seo.build_title(""), f"{seo.SITE_NAME} | {seo.SITE_TAGLINE}")
        self.assertEqual(seo.build_title(None), f"{seo.SITE_NAME} | {seo.SITE_TAGLINE}")

    def test_long_title_is_truncated_inside_the_budget(self):
        title = seo.build_title("A" * 200)
        self.assertLessEqual(len(title), seo.TITLE_MAX)
        self.assertTrue(title.endswith(seo.SITE_NAME))

    def test_description_is_trimmed_to_the_snippet_budget(self):
        description = seo.build_description("word " * 200)
        self.assertLessEqual(len(description), seo.DESCRIPTION_MAX)
        self.assertFalse(description.endswith(" "))

    def test_description_collapses_whitespace_and_uses_the_fallback(self):
        self.assertEqual(seo.build_description("  a\n\n b  "), "a b")
        self.assertEqual(seo.build_description(""), seo.DEFAULT_DESCRIPTION)

    def test_absolute_url_builds_on_the_configured_origin(self):
        self.assertEqual(seo.absolute_url("/shop/"), f"{SITE}/shop/")
        self.assertEqual(seo.absolute_url("shop/"), f"{SITE}/shop/")
        # An already-absolute URL is passed through rather than being re-hosted.
        self.assertEqual(
            seo.absolute_url("https://cdn.test/x.png"), "https://cdn.test/x.png"
        )

    def test_debug_forces_noindex_even_without_an_explicit_flag(self):
        with override_settings(DEBUG=True):
            self.assertFalse(seo.should_index())
            self.assertIn("noindex", seo.robots_meta())

    def test_production_indexes_unless_told_otherwise(self):
        with override_settings(DEBUG=False):
            self.assertTrue(seo.should_index())
            self.assertIn("noindex", seo.robots_meta(noindex=True))

    def test_private_prefixes_match_every_real_private_area(self):
        for path in (
            "/admin/", "/admin-dashboard/orders/", "/account/", "/cart/",
            "/checkout/", "/login/", "/logout/", "/register/",
            "/forgot-password/", "/reset-password/",
        ):
            self.assertTrue(seo.is_private_path(path), path)

    def test_public_paths_are_not_treated_as_private(self):
        for path in ("/", "/shop/", "/about/", "/contact/", "/premium-denim-jeans/"):
            self.assertFalse(seo.is_private_path(path), path)

    def test_json_ld_cannot_close_the_script_element_early(self):
        payload = seo.json_ld({"name": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", payload)
        # The value survives intact, so the escaping does not corrupt real content.
        self.assertEqual(json.loads(payload)["name"], "</script><script>alert(1)</script>")


@override_settings(SITE_URL=SITE)
class SeoHeadTagTests(SeoCatalogMixin, TestCase):
    """The rendered head section, checked over real HTTP responses."""

    def get(self, path, **params):
        response = self.client.get(path, params)
        self.assertEqual(response.status_code, 200, path)
        return response.content.decode()

    def test_every_public_page_emits_the_core_head_tags(self):
        for name in ("store:home", "store:shop", "store:about", "store:contact"):
            with self.subTest(page=name):
                html = self.get(reverse(name))
                self.assertTrue(title_of(html))
                self.assertIsNotNone(meta_content(html, "name", "description"))
                self.assertIsNotNone(meta_content(html, "property", "og:title"))
                self.assertIsNotNone(meta_content(html, "property", "og:image"))
                self.assertIsNotNone(meta_content(html, "name", "twitter:card"))
                self.assertIn("index", meta_content(html, "name", "robots"))

    def test_canonical_is_absolute_and_self_referencing(self):
        for name in ("store:home", "store:shop", "store:about", "store:contact"):
            with self.subTest(page=name):
                path = reverse(name)
                self.assertEqual(canonical_of(self.get(path)), SITE + path)

    def test_titles_are_unique_across_public_pages(self):
        titles = {
            title_of(self.get(reverse(name)))
            for name in ("store:home", "store:shop", "store:about", "store:contact")
        }
        self.assertEqual(len(titles), 4, f"duplicate titles: {titles}")

    def test_descriptions_are_unique_across_public_pages(self):
        descriptions = {
            meta_content(self.get(reverse(name)), "name", "description")
            for name in ("store:home", "store:shop", "store:about", "store:contact")
        }
        self.assertEqual(len(descriptions), 4, f"duplicates: {descriptions}")

    def test_every_description_fits_the_snippet_budget(self):
        for name in ("store:home", "store:shop", "store:about", "store:contact"):
            with self.subTest(page=name):
                length = len(meta_content(self.get(reverse(name)), "name", "description"))
                self.assertLessEqual(length, seo.DESCRIPTION_MAX)

    def test_homepage_declares_the_organization_and_the_site(self):
        html = self.get(reverse("store:home"))
        self.assertEqual(len(node_of_type(html, "Organization")), 1)
        website = node_of_type(html, "WebSite")[0]
        self.assertEqual(website["name"], seo.SITE_NAME)

    def test_product_page_uses_the_product_name(self):
        self.assertIn("Premium Denim Jeans", title_of(self.product_page()))

    def test_product_json_ld_only_states_visible_facts(self):
        node = self.product_node(self.product_page())
        self.assertEqual(node["name"], "Premium Denim Jeans")
        self.assertEqual(node["offers"]["priceCurrency"], "BDT")
        self.assertEqual(node["offers"]["price"], "2499.00")
        self.assertEqual(node["offers"]["availability"], "https://schema.org/InStock")
        self.assertEqual(node["sku"], "EZ-JEANS-32-NAVY")

    def test_no_rating_is_claimed_without_approved_reviews(self):
        self.assertNotIn("aggregateRating", self.product_node(self.product_page()))

    def test_approved_reviews_produce_a_rating_node(self):
        for _ in range(3):
            self.add_review(rating=5)
        rating = self.product_node(self.product_page())["aggregateRating"]
        self.assertEqual(rating["reviewCount"], "3")
        self.assertEqual(rating["bestRating"], "5")

    def test_unapproved_reviews_do_not_produce_a_rating_node(self):
        self.add_review(rating=1, approved=False)
        self.assertNotIn("aggregateRating", self.product_node(self.product_page()))

    def test_out_of_stock_product_is_marked_unavailable(self):
        ProductVariant.objects.filter(product=self.product).update(stock=0)
        node = self.product_node(self.product_page())
        self.assertEqual(node["offers"]["availability"], "https://schema.org/OutOfStock")

    def test_breadcrumbs_are_rendered_and_match_the_json_ld(self):
        html = self.product_page()
        crumbs = node_of_type(html, "BreadcrumbList")
        self.assertEqual(len(crumbs), 1)
        names = [i["name"] for i in crumbs[0]["itemListElement"]]
        self.assertEqual(names, ["Home", "Shop", "Jeans", "Premium Denim Jeans"])
        # The same trail is visible in the page body, so the markup is not orphaned.
        self.assertIn('aria-label="Breadcrumb"', html)


    def test_breadcrumbs_need_at_least_two_crumbs(self):
        self.assertEqual(seo.breadcrumb_json_ld([("Home", "/")]), {})
        node = seo.breadcrumb_json_ld([("Home", "/"), ("Shop", "/shop/")])
        self.assertEqual(node["@type"], "BreadcrumbList")
        self.assertEqual(node["itemListElement"][0]["position"], 1)

