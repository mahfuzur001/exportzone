"""Sitemaps for the public storefront.

Only genuinely indexable, canonical URLs are listed. Authentication, the admin
site, the store console, the cart, checkout and account pages are excluded
because they are private or per-visitor.

Filtered, sorted and searched shop views are excluded too, because those pages
carry a ``noindex`` tag: publishing a URL in the sitemap that asks not to be
indexed is a contradiction a crawler has to resolve. Deep pagination is left out
as well, since ``/shop/`` links to it through ``?page=`` and the paginated pages
are self-canonical; listing them adds no discovery that the pagination links do
not already provide.
"""

from datetime import datetime
import os

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.core import seo


class SiteUrlMixin:
    """Force every sitemap entry onto the canonical origin from ``SITE_URL``.

    Django resolves a sitemap's domain from ``django.contrib.sites`` or, failing
    that, from the incoming request. Both are wrong for a crawler: a staging host, a
    preview domain or a proxy-reported ``http`` scheme would all be published as
    canonical URLs, and the sitemap would then disagree with the ``<link
    rel="canonical">`` tags on the same pages. Reading the same setting the canonical
    tags read keeps the two in step.
    """

    def get_protocol(self, protocol=None):
        return seo.site_url().split("://", 1)[0] or "https"

    def get_domain(self, site=None):
        origin = seo.site_url()
        return origin.split("://", 1)[-1]


class StaticViewSitemap(SiteUrlMixin, Sitemap):
    """The hand-written public pages: home, shop, about, contact."""

    priority = 0.6
    changefreq = "weekly"

    # URL name -> the template that renders it. The mapping is explicit because the
    # homepage's template lives in a different app directory from the rest, so the
    # name cannot be derived from the route.
    PAGES = {
        "store:home": "core/home.html",
        "store:shop": "store/shop.html",
        "store:about": "store/about.html",
        "store:contact": "store/contact.html",
    }

    def items(self):
        return list(self.PAGES)

    def location(self, item):
        return reverse(item)

    def lastmod(self, item):
        # These pages have no database row to date them from, so report the
        # newest mtime among the templates that make up the page. A missing
        # template returns None, which simply omits <lastmod> for that entry.
        from django.template.loader import get_template

        try:
            origin = get_template(self.PAGES[item]).origin
        except Exception:
            return None
        if origin is None:
            return None
        try:
            mtime = os.path.getmtime(origin.name)
        except OSError:
            return None
        return datetime.fromtimestamp(mtime).replace(microsecond=0)


class ProductSitemap(SiteUrlMixin, Sitemap):
    """Every active product, newest first so the catalog refreshes predictably."""

    changefreq = "daily"
    priority = 0.8

    def items(self):
        from apps.store.models import Product

        return Product.objects.filter(is_active=True).only("slug", "updated_at")

    def location(self, item):
        return reverse("store:product_detail", kwargs={"slug": item.slug})

    def lastmod(self, item):
        return item.updated_at
