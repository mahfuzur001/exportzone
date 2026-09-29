from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.store.models import Category, Product, ProductVariant

JEANS_SIZES = ["28", "30", "32", "34", "36", "38", "40", "42"]
TOP_SIZES = ["S", "M", "L", "XL", "XXL"]
JEANS_COLORS = ["BLUE", "BLACK", "NAVY", "GRAY"]
TOP_COLORS = ["BLACK", "BLUE", "NAVY", "WHITE", "GRAY", "BEIGE", "GREEN"]

CATEGORIES = [
    ("Jeans", "Slim, straight and relaxed fit premium denim jeans."),
    ("Shirts", "Formal and casual shirts for every occasion."),
    ("Polo T-Shirts", "Classic pique polo t-shirts with premium finishing."),
    ("T-Shirts", "Soft, breathable cotton t-shirts for everyday wear."),
    ("Chinos", "Smart-casual chinos in versatile neutral tones."),
    ("Jackets", "Lightweight jackets and layering pieces."),
    ("Accessories", "Belts, caps and everyday essentials."),
]

PRODUCTS = [
    ("Jeans", "Classic Slim Jeans", "1899.00", "Tailored slim-fit denim with a comfortable stretch weave.", True, JEANS_SIZES, JEANS_COLORS),
    ("Jeans", "Straight Fit Denim", "1799.00", "Timeless straight-fit jeans in washed indigo denim.", False, JEANS_SIZES, JEANS_COLORS),
    ("Jeans", "Relaxed Comfort Jeans", "1699.00", "Relaxed-fit jeans designed for all-day comfort.", False, JEANS_SIZES, JEANS_COLORS),
    ("Shirts", "Oxford Formal Shirt", "1399.00", "Crisp oxford weave shirt for office and events.", True, TOP_SIZES, TOP_COLORS),
    ("Shirts", "Casual Check Shirt", "1299.00", "Soft flannel check shirt for laid-back days.", False, TOP_SIZES, TOP_COLORS),
    ("Polo T-Shirts", "Heritage Polo T-Shirt", "999.00", "Classic pique polo with a ribbed collar.", True, TOP_SIZES, TOP_COLORS),
    ("Polo T-Shirts", "Classic Pique Polo", "1099.00", "Breathable polo shirt with a modern regular fit.", False, TOP_SIZES, TOP_COLORS),
    ("T-Shirts", "Essential Crew T-Shirt", "699.00", "Premium cotton crew-neck tee, built to last.", True, TOP_SIZES, TOP_COLORS),
    ("Chinos", "Tailored Chinos", "1499.00", "Flat-front chinos with a clean tailored silhouette.", False, TOP_SIZES, TOP_COLORS),
    ("Jackets", "Light Bomber Jacket", "2590.00", "Lightweight bomber jacket for transitional weather.", False, TOP_SIZES, ["BLACK", "NAVY", "GREEN", "BEIGE"]),
]

STOCK_PER_VARIANT = 12


class Command(BaseCommand):
    help = (
        "Seed the catalog with demo categories, products and stock variants. "
        "Idempotent: safe to run more than once."
    )

    def handle(self, *args, **options):
        categories_created = 0
        for name, description in CATEGORIES:
            _, created = Category.objects.get_or_create(
                name=name,
                defaults={"slug": slugify(name), "description": description},
            )
            if created:
                categories_created += 1

        products_created = 0
        variants_created = 0
        for category_name, name, price, description, featured, sizes, colors in PRODUCTS:
            category = Category.objects.get(name=category_name)
            product, created = Product.objects.get_or_create(
                slug=slugify(name),
                defaults={
                    "category": category,
                    "name": name,
                    "description": description,
                    "base_price": Decimal(price),
                    "featured": featured,
                    "is_active": True,
                },
            )
            if created:
                products_created += 1
            sku_prefix = slugify(name).upper()
            for size in sizes:
                for color in colors:
                    _, created = ProductVariant.objects.get_or_create(
                        product=product,
                        size=size,
                        color=color,
                        defaults={
                            "stock": STOCK_PER_VARIANT,
                            "sku": f"{sku_prefix}-{size}-{color}"[:80],
                        },
                    )
                    if created:
                        variants_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                "seed_data complete: "
                f"{categories_created} categories, "
                f"{products_created} products, "
                f"{variants_created} variants created "
                f"(totals: {Category.objects.count()} categories, "
                f"{Product.objects.count()} products, "
                f"{ProductVariant.objects.count()} variants)."
            )
        )