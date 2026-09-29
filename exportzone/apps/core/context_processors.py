"""Template context shared by every page.

Kept deliberately small: anything that costs a database query belongs in a view,
not here, because this runs for all four error pages as well as normal responses.
"""

from django.conf import settings

from .seo import (
    DEFAULT_DESCRIPTION,
    PRIVATE_PREFIXES,
    SITE_NAME,
    SITE_TAGLINE,
    site_url,
)


def seo(request):
    """Brand-level SEO values that never change per page.

    Page-specific values (title, description, canonical, robots, JSON-LD) are
    supplied by the view or by ``{% push_seo %}``; the ``{% seo_meta %}`` tag in
    ``base.html`` merges the two.
    """
    return {
        "seo_site_name": SITE_NAME,
        "seo_tagline": SITE_TAGLINE,
        "seo_default_description": DEFAULT_DESCRIPTION,
        "seo_site_url": site_url(),
        "seo_language": getattr(settings, "LANGUAGE_CODE", "en-us").split("-")[0],
        "seo_private_prefixes": PRIVATE_PREFIXES,
    }
