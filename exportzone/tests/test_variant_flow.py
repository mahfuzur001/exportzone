"""End-to-end tests for the size + colour variant purchase flow.

The storefront picker lets a shopper choose a size and a colour independently;
the rendered <option> elements carry the matching variant, and the chosen
variant travels through cart, checkout and order snapshots.
"""

import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import CartItem
from apps.orders.models import Order, OrderItem
from apps.store.models import Category, Product, ProductVariant

OPTION_PATTERN = re.compile(
    r'<option value="(?P<value>\d+)" data-size="(?P<size>[^"]*)" data-color="(?P<color>[^"]*)" '
    r'data-stock="(?P<stock>\d+)"\s*(?P<disabled>disabled)?\s*>'
)


class SizeColourVariantFlowTests(TestCase):
    password = "A-strong-passphrase-42"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="shopper@example.com",
            phone="01712345678",
            full_name="Shopper One",
            password=self.password,
        )
        category = Category.objects.create(name="Shirts", slug="shirts")
        self.product = Product.objects.create(
            category=category,
            name="Oxford Shirt",
            slug="oxford-shirt",
            description="Crisp oxford weave shirt.",
            base_price=Decimal("1399.00"),
        )
        self.variants = {}
        for size in ("S", "M", "L", "XL"):
            for color in ("BLACK", "BLUE"):
                self.variants[(size, color)] = ProductVariant.objects.create(
                    product=self.product,
                    size=size,
                    color=color,
                    stock=4,
                    sku=f"OX-{size}-{color}",
                )
        # One combination is sold out: it must be unpickable, while the same size
        # in another colour stays available.
        sold_out = self.variants[("L", "BLUE")]
        sold_out.stock = 0
        sold_out.save(update_fields=["stock"])
        self.client.force_login(self.user)

    def product_page(self):
        return self.client.get(reverse("store:product_detail", kwargs={"slug": self.product.slug}))

    def variant_options(self, response):
        return [
            {
                "value": match.group("value"),
                "size": match.group("size"),
                "color": match.group("color"),
                "stock": int(match.group("stock")),
                "disabled": bool(match.group("disabled")),
            }
            for match in OPTION_PATTERN.finditer(response.content.decode())
        ]

    def option_for(self, response, size, color):
        return next(
            option for option in self.variant_options(response) if option["size"] == size and option["color"] == color
        )

    def add_to_cart(self, variant, quantity=1, next_url=None):
        payload = {"product_id": self.product.pk, "variant_id": variant.pk, "quantity": str(quantity)}
        if next_url:
            payload["next"] = next_url
        return self.client.post(reverse("cart:add"), payload)

    def checkout(self):
        return self.client.post(
            reverse("orders:checkout"),
            {
                "full_name": "Shopper One",
                "phone": "01712345678",
                "address": "12 Export Road",
                "area": "Meherpur Sadar",
                "payment_method": "COD",
                "delivery_option": "HOME_DELIVERY",
            },
        )

    def test_size_and_colour_choices_follow_spec_order(self):
        response = self.product_page()
        self.assertEqual(response.status_code, 200)

        # Button order must be S, M, L, XL - not the alphabetical L, M, S, XL.
        size_buttons = re.findall(r'class="variant-btn[^"]*" data-size="([^"]+)"', response.content.decode())
        self.assertEqual(list(dict.fromkeys(size_buttons)), ["S", "M", "L", "XL"])

        # Colour buttons follow the catalogue colour order, not the alphabet.
        color_buttons = re.findall(r'data-color="([^"]+)"', response.content.decode())
        self.assertEqual(list(dict.fromkeys(color_buttons))[:2], ["BLACK", "BLUE"])

        # Options list the smallest size first, colours in catalogue order within it.
        options = self.variant_options(response)
        self.assertEqual(
            [(option["size"], option["color"]) for option in options][:4],
            [("S", "BLACK"), ("S", "BLUE"), ("M", "BLACK"), ("M", "BLUE")],
        )

    def test_picker_exposes_every_size_and_colour_combination(self):
        options = self.variant_options(self.product_page())
        self.assertEqual(len(options), len(self.variants))
        self.assertEqual({(option["size"], option["color"]) for option in options}, set(self.variants))

    def test_sold_out_combination_is_disabled_but_other_colour_is_available(self):
        response = self.product_page()
        self.assertTrue(self.option_for(response, "L", "BLUE")["disabled"])
        self.assertFalse(self.option_for(response, "L", "BLACK")["disabled"])

        # Posting the sold-out variant directly is refused server-side too.
        response = self.add_to_cart(self.variants[("L", "BLUE")])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CartItem.objects.exists())

    def test_selected_size_and_colour_are_added_to_cart(self):
        chosen = self.option_for(self.product_page(), "M", "BLUE")
        self.assertEqual(chosen["value"], str(self.variants[("M", "BLUE")].pk))

        response = self.add_to_cart(self.variants[("M", "BLUE")], quantity=2, next_url=reverse("cart:detail"))
        self.assertRedirects(response, reverse("cart:detail"))

        item = CartItem.objects.get()
        self.assertEqual(item.product_variant, self.variants[("M", "BLUE")])
        self.assertEqual(item.quantity, 2)

        cart_page = self.client.get(reverse("cart:detail"))
        self.assertContains(cart_page, "Size M")
        self.assertContains(cart_page, self.variants[("M", "BLUE")].sku)

    def test_two_combinations_of_one_product_stay_separate_items(self):
        self.add_to_cart(self.variants[("M", "BLUE")], quantity=1)
        self.add_to_cart(self.variants[("S", "BLACK")], quantity=3)
        self.add_to_cart(self.variants[("M", "BLUE")], quantity=1)

        self.assertEqual(CartItem.objects.count(), 2)
        self.assertEqual(CartItem.objects.get(product_variant=self.variants[("M", "BLUE")]).quantity, 2)
        self.assertEqual(CartItem.objects.get(product_variant=self.variants[("S", "BLACK")]).quantity, 3)

    def test_quantity_beyond_stock_is_rejected(self):
        self.add_to_cart(self.variants[("S", "BLACK")], quantity=4)
        response = self.add_to_cart(self.variants[("S", "BLACK")], quantity=1)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CartItem.objects.get().quantity, 4)
        self.assertFalse(Order.objects.exists())

    def test_size_and_colour_survive_cart_to_checkout_to_order(self):
        self.add_to_cart(self.variants[("M", "BLUE")], quantity=2)
        self.add_to_cart(self.variants[("S", "BLACK")], quantity=1)

        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)

        snapshots = {(item.size_snapshot, item.color_snapshot): item for item in OrderItem.objects.all()}
        self.assertEqual(set(snapshots), {("M", "BLUE"), ("S", "BLACK")})
        self.assertEqual(snapshots[("M", "BLUE")].quantity, 2)
        self.assertEqual(snapshots[("M", "BLUE")].product_name_snapshot, "Oxford Shirt")
        self.assertEqual(snapshots[("M", "BLUE")].product_variant, self.variants[("M", "BLUE")])
        self.assertEqual(snapshots[("M", "BLUE")].subtotal, Decimal("2798.00"))

        # Only the ordered variants lose stock.
        self.variants[("M", "BLUE")].refresh_from_db()
        self.variants[("S", "BLACK")].refresh_from_db()
        self.variants[("L", "BLACK")].refresh_from_db()
        self.assertEqual(self.variants[("M", "BLUE")].stock, 2)
        self.assertEqual(self.variants[("S", "BLACK")].stock, 3)
        self.assertEqual(self.variants[("L", "BLACK")].stock, 4)

        # Confirmation page and order history both name the exact size and colour.
        order = Order.objects.get()
        for url in (
            reverse("orders:confirmation", kwargs={"order_number": order.order_number}),
            reverse("orders:detail", kwargs={"order_number": order.order_number}),
        ):
            page = self.client.get(url)
            self.assertContains(page, "Oxford Shirt")
            self.assertContains(page, "Qty 2")

