from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.store.models import Category, Product, ProductVariant

from .models import Cart, CartItem


class CartTests(TestCase):
    password = "A-strong-passphrase-42"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="cart@example.com",
            phone="01712345678",
            full_name="Cart Member",
            password=self.password,
        )
        self.other_user = get_user_model().objects.create_user(
            email="other@example.com",
            phone="01812345678",
            full_name="Other Member",
            password=self.password,
        )
        category = Category.objects.create(name="Jeans", slug="jeans")
        self.product = Product.objects.create(
            category=category,
            name="Premium Jeans",
            slug="premium-jeans",
            description="Premium denim.",
            base_price=Decimal("2499.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="32",
            color="BLUE",
            stock=5,
            sku="JEANS-32-BLUE",
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.product,
            size="34",
            color="BLACK",
            stock=0,
            sku="JEANS-34-BLACK",
        )
        self.client.force_login(self.user)

    def test_cart_creation_and_one_to_one_user_relation(self):
        cart = Cart.for_user(self.user)
        self.assertEqual(Cart.for_user(self.user).pk, cart.pk)
        with self.assertRaises(ValidationError):
            Cart(user=self.user).full_clean()

    def test_cart_item_creation_and_duplicate_constraint(self):
        cart = Cart.for_user(self.user)
        item = CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=2)
        self.assertEqual(item.subtotal, Decimal("4998.00"))
        with self.assertRaises(ValidationError):
            CartItem(cart=cart, product_variant=self.variant, quantity=1).full_clean()

    def test_quantity_must_be_positive(self):
        cart = Cart.for_user(self.user)
        with self.assertRaises(ValidationError):
            CartItem(cart=cart, product_variant=self.variant, quantity=0).full_clean()

    def test_anonymous_user_is_redirected_for_cart_page_and_add(self):
        self.client.logout()
        response = self.client.get(reverse("cart:detail"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('cart:detail')}")
        response = self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 1})
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('store:shop')}")

    def test_authenticated_user_can_add_variant(self):
        response = self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 2})
        self.assertRedirects(response, reverse("store:product_detail", kwargs={"slug": self.product.slug}))
        item = CartItem.objects.get(cart__user=self.user)
        self.assertEqual(item.quantity, 2)

    def test_existing_item_quantity_increases(self):
        self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 2})
        self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 2})
        self.assertEqual(CartItem.objects.get(cart__user=self.user).quantity, 4)

    def test_invalid_variant_and_product_mismatch_are_rejected(self):
        response = self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.other_variant.pk, "quantity": 1})
        self.assertRedirects(response, reverse("store:product_detail", kwargs={"slug": self.product.slug}))
        other_category = Category.objects.create(name="Shirts", slug="shirts")
        other_product = Product.objects.create(category=other_category, name="Shirt", slug="shirt", description="Shirt", base_price=Decimal("100.00"))
        response = self.client.post(reverse("cart:add"), {"product_id": other_product.pk, "variant_id": self.variant.pk, "quantity": 1})
        self.assertEqual(response.status_code, 404)

    def test_inactive_and_out_of_stock_products_are_rejected(self):
        self.product.is_active = False
        self.product.save()
        response = self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 1})
        self.assertEqual(response.status_code, 404)
        self.product.is_active = True
        self.product.save()
        response = self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.other_variant.pk, "quantity": 1})
        self.assertRedirects(response, reverse("store:product_detail", kwargs={"slug": self.product.slug}))

    def test_quantity_above_stock_is_rejected(self):
        response = self.client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 6})
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())
        self.assertRedirects(response, reverse("store:product_detail", kwargs={"slug": self.product.slug}))

    def test_cart_page_totals_and_empty_state(self):
        response = self.client.get(reverse("cart:detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Cart is Empty")
        CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=2)
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, "৳4998.00")
        self.assertContains(response, "৳0.00")
        self.assertContains(response, "৳4998.00")

    def test_update_can_increase_and_decrease_but_not_exceed_stock(self):
        item = CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=2)
        response = self.client.post(reverse("cart:update", kwargs={"item_id": item.pk}), {"quantity": 3})
        self.assertRedirects(response, reverse("cart:detail"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)
        self.client.post(reverse("cart:update", kwargs={"item_id": item.pk}), {"quantity": 1})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)
        self.client.post(reverse("cart:update", kwargs={"item_id": item.pk}), {"quantity": 6})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_invalid_update_quantity_is_rejected(self):
        item = CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=2)
        self.client.post(reverse("cart:update", kwargs={"item_id": item.pk}), {"quantity": "bad"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_remove_requires_post_and_ownership(self):
        item = CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=1)
        self.assertEqual(self.client.get(reverse("cart:remove", kwargs={"item_id": item.pk})).status_code, 405)
        other_cart = Cart.for_user(self.other_user)
        other_item = CartItem.objects.create(cart=other_cart, product_variant=self.variant, quantity=1)
        self.client.post(reverse("cart:remove", kwargs={"item_id": other_item.pk}))
        self.assertTrue(CartItem.objects.filter(pk=other_item.pk).exists())
        self.client.post(reverse("cart:remove", kwargs={"item_id": item.pk}))
        self.assertFalse(CartItem.objects.filter(pk=item.pk).exists())

    def test_cart_count_uses_total_quantity(self):
        CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=3)
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, "Cart (3)")

    def test_csrf_protects_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse("cart:add"), {"product_id": self.product.pk, "variant_id": self.variant.pk, "quantity": 1})
        self.assertEqual(response.status_code, 403)

    def test_clear_cart_requires_post_and_only_affects_own_cart(self):
        my_item = CartItem.objects.create(cart=Cart.for_user(self.user), product_variant=self.variant, quantity=2)
        other_item = CartItem.objects.create(cart=Cart.for_user(self.other_user), product_variant=self.variant, quantity=1)

        self.assertEqual(self.client.get(reverse("cart:clear")).status_code, 405)
        self.assertTrue(CartItem.objects.filter(pk=my_item.pk).exists())

        response = self.client.post(reverse("cart:clear"))
        self.assertRedirects(response, reverse("cart:detail"))
        self.assertFalse(CartItem.objects.filter(pk=my_item.pk).exists())
        self.assertTrue(CartItem.objects.filter(pk=other_item.pk).exists())

        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, "Your Cart is Empty")
