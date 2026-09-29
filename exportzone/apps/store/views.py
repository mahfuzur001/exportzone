from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.seo import (
    build_page_seo,
    build_product_seo,
    build_shop_seo,
    organization_json_ld,
    website_json_ld,
)

from .forms import ContactForm
from .models import COLOR_CHOICES, SIZE_CHOICES, Category, Product, ProductVariant


def home(request):
    build_page_seo(
        request,
        {
            "seo_title": f"Premium Denim, Shirts & Polo T-Shirts in Bangladesh",
            # Describes the catalogue and the delivery promise the homepage actually
            # shows, rather than repeating the brand name as a keyword list.
            "seo_description": (
                "Export Zone is a Meherpur clothing house selling premium jeans, shirts "
                "and polo t-shirts in every size, delivered nationwide across Bangladesh."
            ),
            "seo_og_type": "website",
            # The homepage is the only page allowed to declare the site identity; on
            # every other page those two nodes would just repeat the brand name.
            "seo_jsonld": [website_json_ld(), organization_json_ld()],
        },
    )
    base_qs = Product.objects.filter(is_active=True).prefetch_related("images", "variants")
    featured_products = list(base_qs.filter(featured=True).order_by("-created_at")[:4])
    if not featured_products:
        featured_products = list(base_qs.order_by("-created_at")[:4])
    categories = Category.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    )[:4]
    new_arrivals = list(
        base_qs.order_by("-created_at").exclude(pk__in=[p.pk for p in featured_products])[:4]
    )

    return render(request, "core/home.html", {
        "featured_products": featured_products,
        "new_arrivals": new_arrivals,
        "categories": categories,
    })



PAGE_SIZE = 12
SORT_CHOICES = {
    "featured": "-featured",
    "newest": "-created_at",
    "price_low": "base_price",
    "price_high": "-base_price",
    "name_asc": "name",
}


def _active_products_queryset():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related("images", "variants")
    )


def _get_filter_context(request):
    categories = Category.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    ).order_by("name")
    sizes = [value for value, _ in ProductVariant._meta.get_field("size").choices]
    colors = [value for value, _ in ProductVariant._meta.get_field("color").choices]
    selected_category = request.GET.get("category")
    selected_size = request.GET.get("size")
    selected_color = request.GET.get("color")
    selected_sort = request.GET.get("sort", "featured")
    min_price = request.GET.get("min_price", "")
    max_price = request.GET.get("max_price", "")
    q = request.GET.get("q", "")

    return {
        "categories": categories,
        "sizes": sizes,
        "colors": colors,
        "selected_category": selected_category,
        "selected_size": selected_size,
        "selected_color": selected_color,
        "selected_sort": selected_sort if selected_sort in SORT_CHOICES else "featured",
        "min_price": min_price,
        "max_price": max_price,
        "q": q,
    }


def shop(request):
    queryset = _active_products_queryset()
    category = request.GET.get("category")
    size = request.GET.get("size")
    color = request.GET.get("color")
    q = request.GET.get("q", "").strip()
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    sort_key = request.GET.get("sort", "featured")

    if category:
        queryset = queryset.filter(category__slug=category, category__is_active=True)
    if size:
        queryset = queryset.filter(variants__size=size, variants__stock__gt=0)
    if color:
        queryset = queryset.filter(variants__color=color, variants__stock__gt=0)
    if min_price:
        try:
            queryset = queryset.filter(base_price__gte=Decimal(min_price))
        except Exception:
            pass
    if max_price:
        try:
            queryset = queryset.filter(base_price__lte=Decimal(max_price))
        except Exception:
            pass
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__name__icontains=q)
            | Q(variants__sku__icontains=q)
        ).distinct()

    order_by = SORT_CHOICES.get(sort_key, "-featured")
    queryset = queryset.order_by(order_by)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    filter_context = _get_filter_context(request)
    # The SEO builder needs the real Category behind ?category=. The filters already
    # load every active category, so the slug is matched against that list rather
    # than costing an extra query on every listing request.
    selected_slug = filter_context["selected_category"]
    selected_category = next(
        (category for category in filter_context["categories"] if category.slug == selected_slug),
        None,
    )

    context = {
        **filter_context,
        "products": page_obj,
        "page_obj": page_obj,
        "sort_choices": SORT_CHOICES,
        "selected_category_object": selected_category,
        "result_count": paginator.count,
    }
    build_shop_seo(request, context)
    return render(request, "store/shop.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.filter(is_active=True).select_related("category").prefetch_related("images", "variants"),
        slug=slug,
    )
    # Spec order: waist sizes 28-42 and tops S-XXL follow the catalogue sequence, never the alphabet.
    size_rank = {value: index for index, (value, _) in enumerate(SIZE_CHOICES)}
    color_rank = {value: index for index, (value, _) in enumerate(COLOR_CHOICES)}
    variants = sorted(
        product.variants.all(),
        key=lambda variant: (
            size_rank.get(variant.size, len(size_rank)),
            color_rank.get(variant.color, len(color_rank)),
            variant.sku,
        ),
    )
    variants_by_size = sorted(
        {variant.size for variant in variants if variant.stock > 0},
        key=lambda size: size_rank.get(size, len(size_rank)),
    )
    variants_by_color = sorted(
        {variant.color for variant in variants if variant.stock > 0},
        key=lambda color: color_rank.get(color, len(color_rank)),
    )
    color_labels = dict(COLOR_CHOICES)
    color_options = [(value, color_labels.get(value, value)) for value in variants_by_color]
    related_products = list(
        Product.objects.filter(is_active=True, category=product.category)
        .exclude(pk=product.pk)
        .select_related("category")
        .prefetch_related("images", "variants")[:4]
    )
    context = {
        "product": product,
        "variants": variants,
        "available_sizes": variants_by_size,
        "available_colors": variants_by_color,
        "color_options": color_options,
        "related_products": related_products,
        "primary_image": product.primary_image,
        "in_stock_variants": [variant for variant in variants if variant.stock > 0],
    }
    build_product_seo(request, product, context)
    return render(request, "store/product_detail.html", context)


def about(request):
    build_page_seo(
        request,
        {
            "seo_title": "Our Story",
            # Reflects the page's own "Our Story" copy rather than repeating the
            # catalogue wording, so About and Shop are not duplicate content.
            "seo_description": (
                "Learn how Export Zone selects wardrobe essentials for comfort, "
                "durability and timeless style from our clothing house in Meherpur, "
                "Bangladesh."
            ),
        },
    )
    return render(request, "store/about.html")


def contact(request):
    build_page_seo(
        request,
        {
            "seo_title": "Contact Us",
            "seo_description": (
                "Contact Export Zone in Meherpur, Bangladesh with your order or "
                "product question and we will respond as soon as possible."
            ),
        },
    )
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Your message has been sent successfully. We will get back to you soon.",
        )
        return redirect("store:contact")
    return render(request, "store/contact.html", {"form": form})

