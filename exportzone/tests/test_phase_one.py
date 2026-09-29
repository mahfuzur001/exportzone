from django.test import TestCase
from django.urls import reverse


class StorefrontFoundationTests(TestCase):
    def test_home_page_is_available(self):
        response = self.client.get(reverse("store:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Premium quality")

    def test_home_page_uses_the_base_layout(self):
        response = self.client.get(reverse("store:home"))

        self.assertTemplateUsed(response, "base.html")
