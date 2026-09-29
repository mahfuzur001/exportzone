"""Template helpers for the head section.

Pages never assemble meta tags by hand. A template sets the few values that differ
(``{% seo_meta title=... description=... %}`) or inherits the ones its parent already
declared, and this tag layer turns them into escaped markup. Centralising it is what
keeps a canonical URL from ever being emitted without a matching robots directive.
"""

from __future__ import annotations

import json

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.core import seo

register = template.Library()


# Markers a child template can push onto, so a page that extends a layout can still
# override the description without the parent having to know it exists.
_TITLE_KEY = "seo_title"
_DESCRIPTION_KEY = "seo_description"
_CANONICAL_KEY = "seo_canonical"
_IMAGE_KEY = "seo_image"
_NOINDEX_KEY = "seo_noindex"
_TYPE_KEY = "seo_og_type"
_BREADCRUMBS_KEY = "seo_breadcrumbs"
_JSONLD_KEY = "seo_jsonld"

# Maps the public keyword names used in templates onto the flat context keys that
# ``seo_meta`` reads. Views can also set these directly through the ``seo_context``
# context processor, so the two paths stay interchangeable.
_FIELD_MAP = {
    "title": _TITLE_KEY,
    "description": _DESCRIPTION_KEY,
    "canonical": _CANONICAL_KEY,
    "image": _IMAGE_KEY,
    "noindex": _NOINDEX_KEY,
    "og_type": _TYPE_KEY,
    "breadcrumbs": _BREADCRUMBS_KEY,
    "jsonld": _JSONLD_KEY,
}


@register.simple_tag(takes_context=True)
def seo_meta(
    context,
    *,
    title: str = "",
    description: str = "",
    canonical: str = "",
    image=None,
    noindex: bool = False,
    og_type: str = "website",
    breadcrumbs=None,
    jsonld=None,
):
    """Render the complete head markup for one page.

    Values passed here win; anything omitted falls back to what an ancestor template
    already set, so ``base.html`` can stay the single place the defaults live. The
    returned string is marked safe because every interpolated value is escaped here -
    descriptions come from admin-entered product copy and must not be able to inject
    markup or close the tag early.
    """
    request = context.get("request")
    # ``{% push_seo %}`` values are merged here as well as onto the flat context,
    # because Django does not guarantee the order in which a parent's blocks render
    # relative to a child's - reading render_context covers either order.
    stored = context.render_context.get("seo_values", {})

    def resolve(field_key):
        """Read one value from the render context, then from the request.

        ``build_page_seo`` stores a view's values on the request rather than in the
        render context, so a page that sets them in a view and inherits the head
        block from base.html still resolves them here. ``push_seo`` writes to
        ``render_context`` because that is the only store shared between the blocks
        of a parent and a child template.
        """
        context_key = _FIELD_MAP[field_key]
        value = context.get(context_key)
        if value in (None, ""):
            value = getattr(request, context_key, None)
        return value

    def pick(field_key, keyword, default=""):
        if keyword:
            return keyword
        if stored.get(field_key) not in (None, ""):
            return stored[field_key]
        return resolve(field_key) or default

    resolved_title = pick("title", title)
    resolved_description = pick("description", description) or seo.DEFAULT_DESCRIPTION
    # A page may point the canonical somewhere else deliberately (a category filter);
    # otherwise the canonical is this page's own normalised path.
    resolved_canonical = pick("canonical", canonical) or seo.clean_path(request)
    resolved_image = pick("image", image, None)
    page_noindex = bool(noindex or stored.get("noindex") or resolve("noindex"))
    page_type = pick("og_type", og_type) or "website"
    trail = breadcrumbs if breadcrumbs is not None else (
        stored.get("breadcrumbs")
        if stored.get("breadcrumbs") is not None
        else resolve("breadcrumbs")
    )
    extra_nodes = jsonld if jsonld is not None else (
        stored.get("jsonld") if stored.get("jsonld") is not None else resolve("jsonld")
    )

    absolute_canonical = seo.absolute_url(resolved_canonical)
    absolute_image = seo.og_image_url(resolved_image)
    final_title = seo.build_title(resolved_title)
    final_description = seo.build_description(resolved_description)

    # A private or utility route is never indexable, whatever the template asks
    # for. Deriving this from the URL rather than trusting each template means a
    # new login-gated page is protected the day it is written, instead of on the
    # day someone remembers to add noindex=True to it.
    private = bool(request) and seo.is_private_path(request.path)
    page_noindex = page_noindex or private

    parts = [
        f"<title>{escape(final_title)}</title>",
        f'<meta name="description" content="{escape(final_description)}">',
        f'<meta name="robots" content="{escape(seo.robots_meta(noindex=page_noindex))}">',
    ]

    # A canonical tells a search engine "index this URL instead of that one", which
    # is the opposite instruction to noindex. Sending both on a page that must stay
    # out of the index is contradictory, so a private page declares only noindex.
    if not private:
        parts.append(f'<link rel="canonical" href="{escape(absolute_canonical)}">')

    # Open Graph and Twitter carry the same facts as the standard tags; a social
    # crawler that never sees the page body still gets the title, summary and image.
    parts += [
        f'<meta property="og:site_name" content="{escape(seo.SITE_NAME)}">',
        f'<meta property="og:title" content="{escape(final_title)}">',
        f'<meta property="og:description" content="{escape(final_description)}">',
        f'<meta property="og:url" content="{escape(absolute_canonical)}">',
        f'<meta property="og:type" content="{escape(page_type)}">',
        f'<meta property="og:locale" content="en_US">',
        f'<meta property="og:image" content="{escape(absolute_image)}">',
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{escape(final_title)}">',
        f'<meta name="twitter:description" content="{escape(final_description)}">',
        f'<meta name="twitter:image" content="{escape(absolute_image)}">',
    ]

    nodes = [node for node in (extra_nodes or []) if node]
    breadcrumb_node = seo.breadcrumb_json_ld(trail)
    if breadcrumb_node:
        nodes.append(breadcrumb_node)
    for node in nodes:
        parts.append(f'<script type="application/ld+json">{seo.json_ld(node)}</script>')

    return mark_safe("\n    ".join(parts))


@register.simple_tag(takes_context=True)
def push_seo(context, **values):
    """Record SEO values for child templates.

    Layouts call this in their own ``{% block %}`` so a page that extends them only
    has to override the field it actually changes. Only the documented keys are
    accepted, so a typo in a template name fails visibly instead of silently leaving
    the parent's value in place.
    """
    stored = context.render_context.setdefault("seo_values", {})
    stored.update(values)
    # Mirror onto the flat context as well, because ``{% seo_meta %}`` in the parent
    # template may be rendered before this block runs on some template chains.
    for key, mapping in _FIELD_MAP.items():
        if key in values:
            context[mapping] = values[key]
    return ""


@register.simple_tag
def absolute_url(path: str) -> str:
    """Expose the canonical-origin URL builder to templates (schema, share links)."""
    return escape(seo.absolute_url(path))


@register.simple_tag
def product_json_ld_for(product) -> dict:
    """Build the ``Product`` node for a catalogue page.

    Images and variants are read off the prefetched relations the view already
    loaded to render the page, so this adds no queries of its own.
    """
    if not product:
        return {}
    variants = list(product.variants.all())
    in_stock = any(variant.stock > 0 for variant in variants)
    image_urls = [absolute_url(image.image.url) for image in product.images.all() if image.image]
    url = seo.absolute_url(seo.try_reverse("store:product_detail", slug=product.slug))
    return seo.product_json_ld(product, url=url, in_stock=in_stock, image_urls=image_urls)


@register.simple_tag
def organization_json_ld() -> dict:
    """Site identity node, emitted once on the homepage."""
    return seo.organization_json_ld()


@register.simple_tag
def website_json_ld() -> dict:
    """Site name and publisher node, emitted once on the homepage."""
    return seo.website_json_ld()


@register.simple_tag
def breadcrumbs_for(*pairs) -> list[dict]:
    """Build a breadcrumb trail from ``name, url`` template arguments.

    Accepts loose values rather than a structure so a template can write
    ``{% breadcrumbs_for "Shop", shop_url "Category", category_url %}`` and stay
    readable; pairs missing a URL are dropped by :func:`breadcrumb_items`.
    """
    return [list(pair) for pair in pairs if pair]


@register.filter
def seo_json(value) -> str:
    """Serialise a Python object for embedding in a ``<script>`` block."""
    return mark_safe(seo.json_ld(value) if isinstance(value, dict) else json.dumps(value))
