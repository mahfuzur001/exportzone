"""Reusable SEO helpers shared by every public page.

Everything here is deliberately server-side and free of third-party packages: the
head tags are rendered from real page data at request time, so a crawler that does
not execute JavaScript sees the same content a shopper does.

The design is intentionally small. Pages supply the few values that differ, and
everything else (site name, canonical base, Twitter handle, fallbacks) comes from
``settings`` or a constant here. There is no database table: an SEO admin would add
a second source of truth that could silently disagree with the catalogue, and the
catalogue is what has to be right.
"""

from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.text import Truncator

# Search engines truncate around 60 characters for a title and 160 for a
# description. These budgets sit slightly under those limits so the brand suffix
# is never the part that gets cut.
TITLE_MAX = 60
DESCRIPTION_MAX = 160

SITE_NAME = "Export Zone"
SITE_TAGLINE = "Premium Clothing from Meherpur"

DEFAULT_DESCRIPTION = (
    "Export Zone is a Meherpur clothing house selling premium jeans, shirts and "
    "polo t-shirts in every size, delivered nationwide across Bangladesh."
)

# Every prefix below was read off the project's own URLconf (see config/urls.py).
# These are the paths that either hold private data or are pure utility endpoints;
# none of them should ever appear in a search index. Note that /account/ covers
# /account/orders/ and /account/addresses/ as well, so a prefix match is enough.
# Static and media assets are deliberately absent: blocking them stops Google from
# rendering the pages they are needed on.
PRIVATE_PREFIXES = (
    "admin/",
    "admin-dashboard/",
    "account/",
    "cart/",
    "checkout/",
    "order-success/",
    "login/",
    "logout/",
    "register/",
    "forgot-password/",
    "reset-password/",
)


def is_private_path(path: str) -> bool:
    """Whether a request path belongs to a private or utility area of the site."""
    path = (path or "/").lstrip("/")
    if not path:
        return False
    return any(path.startswith(prefix) for prefix in PRIVATE_PREFIXES)


def site_url() -> str:
    """The canonical origin, without a trailing slash.

    ``SITE_URL`` is the single source of truth because it is already required by
    the email layer; deriving the origin from ``request`` instead would make the
    sitemap and the canonical tags disagree whenever a proxy reports a different
    scheme, which is exactly the kind of inconsistency that splits index signals.
    """
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def absolute_url(path: str) -> str:
    """Turn a root-relative path into an absolute URL on the canonical origin.

    Anything already absolute is passed through untouched, so calling this twice
    is harmless. User input never reaches this function: callers pass ``request.path``
    or a reversed URL, and ``SITE_URL`` comes from the environment.
    """
    if not path:
        return site_url() + "/"
    if path.startswith(("http://", "https://", "//")):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return site_url() + path


def clean_path(request) -> str:
    """Return the request path in its canonical form.

    Two URLs for the same page are the most common source of duplicate content on
    a Django site, so canonicalisation normalises the path itself rather than
    merely reading ``request.get_full_path()`` back out.

    The trailing slash is *kept*, because every route in this project's URLconf is
    declared with one (``shop/``, ``about/``, ``product/<slug>/``) and
    ``APPEND_SLASH`` redirects the slashless form here. Dropping it would point
    every canonical at a URL the site only serves through a 301.

    ``None`` is accepted because Django's 500 template is rendered without a
    request in the context; an error page must never raise.
    """
    if request is None:
        return "/"
    path = urlsplit(getattr(request, "path", "/") or "/").path or "/"
    # Collapse accidental duplicate slashes, which a crawler can request directly
    # and which would otherwise be treated as a distinct page.
    while "//" in path:
        path = path.replace("//", "/")
    return path


def build_title(page_title: str | None) -> str:
    """Compose ``<page> | Export Zone`` and keep it inside the title budget.

    A page that already carries the brand name is left alone rather than having
    "Export Zone | Export Zone" appended.
    """
    page_title = (page_title or "").strip()
    if not page_title:
        return f"{SITE_NAME} | {SITE_TAGLINE}"
    if SITE_NAME.lower() in page_title.lower():
        return page_title
    # Reserve room for the separator and brand so the suffix is never truncated.
    budget = TITLE_MAX - len(SITE_NAME) - 3
    if len(page_title) > budget:
        page_title = Truncator(page_title).chars(budget, truncate="…")
    return f"{page_title} | {SITE_NAME}"


def build_description(text: str | None, fallback: str = DEFAULT_DESCRIPTION) -> str:
    """Trim a description to a single readable sentence at search-result length."""
    text = " ".join((text or "").split())
    if not text:
        text = fallback
    if len(text) > DESCRIPTION_MAX:
        text = Truncator(text).chars(DESCRIPTION_MAX, truncate="…")
    return text


def og_image_url(image=None) -> str:
    """Resolve the Open Graph image to an absolute URL.

    Accepts a Django image field/instance or a plain path. Falls back to the brand
    mark in static files so a social card is never missing; the fallback is
    resolved through ``static()`` so it keeps working when the file moves.
    """
    if image:
        url = getattr(image, "url", None) or (image if isinstance(image, str) else None)
        if url:
            return absolute_url(url)
    return absolute_url(static("img/og-default.png"))


def should_index(*, noindex: bool = False) -> bool:
    """Whether this response may be indexed, honouring the DEBUG setting.

    A staging copy of the site must never end up in an index, so DEBUG forces
    noindex globally rather than relying on the host being excluded.
    """
    if getattr(settings, "DEBUG", False):
        return False
    return not noindex


def robots_meta(*, noindex: bool = False, nofollow: bool = False) -> str:
    """Build the ``robots`` meta content for this page."""
    if not should_index(noindex=noindex):
        return "noindex, nofollow"
    return "index, nofollow" if nofollow else "index, follow"


def breadcrumb_items(trail) -> list[dict]:
    """Normalise a breadcrumb trail into JSON-LD-ready ``name``/``url`` pairs."""
    items = []
    for entry in trail or []:
        if isinstance(entry, dict):
            name, path = entry.get("name"), entry.get("url")
        else:
            name, path = entry
        if not name or not path:
            continue
        items.append({"name": str(name), "url": absolute_url(path)})
    return items


def _json_default(value):
    """Make the handful of Django types that reach structured data serialisable."""
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "url"):
        return absolute_url(value.url)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def json_ld(payload: dict) -> str:
    """Serialise structured data for embedding in a ``<script>`` block.

    ``</script>`` is neutralised because a value that ever contains it (a product
    name copied from user input, say) would otherwise close the tag early and
    break out of the script element. The payload is JSON-escaped rather than
    HTML-escaped, since JSON-LD is parsed as JSON instead of being rendered.
    """
    encoded = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return encoded.replace("</", "<\\/")


def try_reverse(name: str, *args, **kwargs) -> str:
    """``reverse`` that returns an empty string instead of raising.

    Used by optional breadcrumbs: a missing route should degrade the markup, not
    take the whole page down.
    """
    try:
        return reverse(name, args=args, kwargs=kwargs or None)
    except NoReverseMatch:
        return ""


def product_json_ld(product, *, url: str, in_stock: bool, image_urls) -> dict:
    """Build a ``Product`` node from catalogue data only.

    Everything emitted here is a fact already visible on the page. The
    ``AggregateRating`` node is omitted unless at least one approved review exists,
    because a rating with a zero review count is invalid structured data and earns
    a rich-result penalty rather than a star rating.
    """
    variants = list(product.variants.all())
    in_stock_variants = [v for v in variants if v.stock > 0]
    # Prefer a purchasable variant's SKU, fall back to any variant, and omit the
    # field entirely when the product has no variants at all.
    representative = in_stock_variants or variants
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "url": url,
        "description": build_description(product.description, fallback=""),
        "sku": representative[0].sku if representative else None,
        "image": list(image_urls),
        "brand": {"@type": "Brand", "name": SITE_NAME},
        "offers": {
            "@type": "Offer",
            "url": url,
            "priceCurrency": "BDT",
            "price": str(product.base_price),
            "availability": (
                "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock"
            ),
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": SITE_NAME},
        },
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "", [])}

    summary = product.rating_summary
    if summary["count"]:
        payload["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(summary["average"]),
            "reviewCount": str(summary["count"]),
            # bestRating/worstRating are required by the specification; without
            # them Google reads the value as a 0-1 scale and rejects the node.
            "bestRating": "5",
            "worstRating": "1",
        }
    return payload


def organization_json_ld() -> dict:
    """The organization identity shown once on the homepage.

    ``Organization`` is used rather than the more specific ``Store``, because the
    pages describe a clothing house that sells online; a ``Store`` node would assert
    a physical retail location the site never claims to have. The address is the one
    the site already publishes in its footer and about page, so nothing is invented.
    """
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": site_url() + "/",
        "description": DEFAULT_DESCRIPTION,
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Meherpur",
            "addressCountry": "BD",
        },
        "currenciesAccepted": "BDT",
    }


def website_json_ld() -> dict:
    """Site-level node declaring the name and the publisher."""
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": site_url() + "/",
        "publisher": {"@type": "Organization", "name": SITE_NAME},
    }


def breadcrumb_json_ld(trail) -> dict:
    """A ``BreadcrumbList`` matching the breadcrumb rendered in the template."""
    items = breadcrumb_items(trail)
    if len(items) < 2:
        # A single crumb is not a trail; emitting it adds noise without meaning.
        return {}
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": item["name"],
                "item": item["url"],
            }
            for index, item in enumerate(items, start=1)
        ],
    }


def build_page_seo(request, values: dict) -> None:
    """Attach a page's SEO values to the request for the head tag to read.

    Views call this instead of passing SEO values through the template context,
    which keeps the render context free of them and means a page cannot forget to
    pass one along to a template that forgot to render it. Values are stored under
    the same flat keys the ``{% seo_meta %}`` tag falls back to, so a template may
    still override any of them explicitly.
    """
    for key, value in (values or {}).items():
        setattr(request, key, value)


def build_product_seo(request, product, context: dict) -> None:
    """Populate a product page's SEO values from the catalogue record alone.

    No admin-editable overrides exist in this project, so the title and description
    are composed from the fields staff already maintain. Doing it here rather than in
    the template keeps the description the crawler reads identical to the one used
    for the structured data, which must not drift apart.
    """

    category = product.category
    path = try_reverse("store:product_detail", slug=product.slug)
    in_stock = any(variant.stock > 0 for variant in product.variants.all())

    context["product_breadcrumbs"] = breadcrumb_items(
        [
            ("Home", try_reverse("store:home")),
            ("Shop", try_reverse("store:shop")),
            (category.name, f"{try_reverse('store:shop')}?category={category.slug}"),
            (product.name, path),
        ]
    )
    context["product_jsonld"] = product_json_ld(
        product,
        url=absolute_url(path),
        in_stock=in_stock,
        image_urls=[image.image.url for image in product.images.all() if image.image],
    )
    build_page_seo(
        request,
        {
            "seo_title": f"{product.name} in {category.name}",
            # The visible page shows the price and the category, so both belong in
            # the snippet; the first sentence of the copy carries the keyword.
            "seo_description": build_description(
                f"{product.name} — {category.name} from {SITE_NAME}. "
                f"৳{product.base_price}. {product.description}"
            ),
            "seo_canonical": path,
            "seo_og_type": "product",
            "seo_breadcrumbs": context["product_breadcrumbs"],
            "seo_jsonld": [context["product_jsonld"]],
            "seo_image": product.primary_image,
        },
    )



# Filter and sort parameters that narrow the shop listing. Each one produces a
# different product set behind the same `/shop/` path, so a listing carrying any of
# them is a duplicate of the unfiltered page unless it is a category (see below).
SHOP_FILTER_PARAMS = ("q", "size", "color", "min_price", "max_price", "sort", "page")


def build_shop_seo(request, context: dict) -> None:
    """Set the listing page's SEO values, honouring filters and pagination.

    Three cases are treated differently, because they are three different kinds of
    page rather than three flavours of the same one:

    * A **category** (``?category=jeans``) is a genuine landing page with its own
      products, so it is indexable and self-canonical.
    * A **page number** (``?page=2``) is the only way a crawler reaches the products
      past the first page, so it is indexable and self-canonical too. Pointing page 2
      at page 1 would strand every product on it - Google states plainly that each
      page in a sequence should list itself and canonicalise to itself.
    * Everything else (a text search, a size or price filter, a sort order) is a
      slice of the same catalogue behind the same path. Those are ``noindex`` and
      canonicalise back to the clean listing, which keeps them crawlable for
      discovery without letting them compete in the index.

    A category keeps its own identity through pagination, so ``?category=jeans&page=2``
    canonicalises to itself rather than back to the unfiltered shop.
    """
    params = request.GET
    category_slug = (params.get("category") or "").strip()
    page_number = (params.get("page") or "").strip()
    listing_path = try_reverse("store:shop")

    # ``page`` is deliberately absent here: pagination is self-canonical, not a
    # duplicate of page one.
    is_filtered = any(
        (params.get(name) or "").strip()
        for name in SHOP_FILTER_PARAMS
        if name != "page"
    )
    is_deep_page = page_number not in ("", "1")
    category = context.get("selected_category_object") if category_slug else None

    # Build the canonical for the listing as it stands, so a category survives paging
    # and a deep page keeps its own number.
    listing_query = {}
    if category is not None:
        listing_query["category"] = category.slug
    if is_deep_page:
        listing_query["page"] = page_number
    listing_url = listing_path + (f"?{urlencode(listing_query)}" if listing_query else "")

    if category is not None:
        # A real category page: indexable, with its own canonical and title.
        if is_filtered:
            # Category plus a size/price/sort filter is still a slice, not a landing
            # page, so it drops back to the plain category URL.
            build_page_seo(
                request,
                {
                    "seo_title": f"{category.name} — Buy Online in Bangladesh",
                    "seo_description": build_description(
                        f"Shop {category.name} from {SITE_NAME}. Premium quality, "
                        f"nationwide delivery across Bangladesh, cash on delivery."
                    ),
                    "seo_canonical": f"{listing_path}?category={category.slug}",
                    "seo_noindex": True,
                },
            )
            return
        page_suffix = f" — Page {page_number}" if is_deep_page else ""
        build_page_seo(
            request,
            {
                "seo_title": f"{category.name} — Buy Online in Bangladesh{page_suffix}",
                "seo_description": build_description(
                    f"Shop {category.name} from {SITE_NAME}. Premium quality, "
                    f"nationwide delivery across Bangladesh, cash on delivery."
                ),
                "seo_canonical": listing_url,
                "seo_noindex": False,
                "seo_breadcrumbs": breadcrumb_items(
                    [
                        ("Home", try_reverse("store:home")),
                        ("Shop", listing_path),
                        (category.name, f"{listing_path}?category={category.slug}"),
                    ]
                ),
            },
        )
        return

    if not is_filtered and not is_deep_page:
        # Unfiltered, un-paginated shop: the canonical listing page.
        build_page_seo(
            request,
            {
                "seo_title": "Shop All Clothing — Denim, Shirts & Polo T-Shirts",
                "seo_description": (
                    "Browse the full Export Zone catalogue: premium jeans, shirts and "
                    "polo t-shirts for men, delivered across Bangladesh with cash on "
                    "delivery."
                ),
                "seo_canonical": listing_path,
                "seo_noindex": False,
            },
        )
        return

    # A bare ?page=2 is the paginated shop, which stays indexable and self-canonical.
    if not is_filtered:
        build_page_seo(
            request,
            {
                "seo_title": f"Shop All Clothing — Page {page_number}",
                "seo_description": (
                    f"Page {page_number} of the Export Zone catalogue: premium jeans, "
                    "shirts and polo t-shirts, delivered across Bangladesh."
                ),
                "seo_canonical": listing_url,
                "seo_noindex": False,
            },
        )
        return

    # A genuine filter, sort or search: crawlable, but never indexed on its own.
    # Canonicalising back to the clean listing tells a crawler which of the
    # near-identical slices is the one worth keeping.
    build_page_seo(
        request,
        {
            "seo_title": (
                f"Search results for “{params.get('q').strip()}”"
                if (params.get("q") or "").strip()
                else "Filtered Catalogue"
            ),
            "seo_description": (
                f"Showing {context.get('result_count', 0)} matching Export Zone products. "
                "Refine by size, colour and price, with nationwide delivery."
            ),
            "seo_canonical": (
                f"{listing_path}?category={category.slug}" if category is not None else listing_path
            ),
            "seo_noindex": True,
        },
    )

