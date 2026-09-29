"""Response middleware that keeps crawlers out of the private parts of the site.

A meta robots tag is only seen by a crawler if it fetches and parses the page. That is
not something a crawler will always do: a URL that answers with a redirect, a 404 or
an error may never be rendered at all, and the tag is then simply absent - which
leaves those URLs free to be indexed. The ``X-Robots-Tag`` header travels with the
response itself, so it applies whether or not a body was ever produced.
"""

from django.utils.deprecation import MiddlewareMixin

from . import seo


class NoIndexPrivatePagesMiddleware(MiddlewareMixin):
    """Add ``X-Robots-Tag: noindex`` to responses that must never be indexed."""

    # Error and redirect responses have no template to carry the meta tag, and these
    # are exactly the URLs that most need the instruction.
    NO_INDEX_STATUSES = frozenset({301, 302, 303, 307, 308, 401, 403, 404, 410, 500, 503})

    def process_response(self, request, response):
        if not self._should_block(request, response):
            return response

        existing = response.get("X-Robots-Tag", "").strip()
        directive = "noindex, follow"
        if existing and directive not in existing:
            directive = f"{existing}, {directive}"
        response["X-Robots-Tag"] = directive
        return response

    @classmethod
    def _should_block(cls, request, response) -> bool:
        if response.status_code in cls.NO_INDEX_STATUSES:
            return True
        # A private URL is private whatever it returns, so a 200 there still must
        # not be indexed.
        return seo.is_private_path(request.path)
