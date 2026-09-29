"""Root URL routing for Export Zone."""

from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

from apps.core.sitemaps import ProductSitemap, StaticViewSitemap

# A single flat sitemap index is simpler for crawlers than a chained one and keeps
# /sitemap.xml as the single entry point the robots file points at.
sitemaps = {"pages": StaticViewSitemap, "products": ProductSitemap}


urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin-dashboard/", include("apps.admin_dashboard.urls", namespace="admin_dashboard")),
    path("cart/", include("apps.cart.urls", namespace="cart")),
    # Content-type must be text/plain; TemplateResponse would send text/html and
    # some crawlers ignore a robots.txt served with the wrong type.
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots",
    ),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("", include("apps.orders.urls", namespace="orders")),
    path("", include("apps.store.urls")),
    path("", include("apps.accounts.urls", namespace="accounts")),
]


# Uploaded images (media/) and collected assets (staticfiles/) are normally
# handed out by nginx or Apache. Shared hosting cannot be relied on to do that,
# so Django serves them itself in production too - and during development the
# runserver/staticfiles app already covers /static/, which is why that branch
# only adds the media route. Set SERVE_STATIC_WITH_DJANGO=False once a real web
# server owns both prefixes; the .htaccess shipped with the deployment package
# already blocks everything that must never be downloadable.
if settings.DEBUG:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}
        )
    ]
elif settings.SERVE_STATIC_WITH_DJANGO:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}
        ),
        re_path(
            r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}
        ),
    ]
