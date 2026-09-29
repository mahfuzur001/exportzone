"""Environment-driven Django settings for Export Zone."""

from __future__ import annotations

import os
from pathlib import Path

from django.utils.crypto import get_random_string
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def _truthy(value: str) -> bool:
    """Return True for the conventional truthy spellings (1/true/yes/on)."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Settings precedence, and why it is not a one-liner:
#
#   DOTENV_OVERRIDE unset or 1  -> the project's .env wins (local default)
#   DOTENV_OVERRIDE=0           -> real environment variables win
#
# The file wins by default because a generically named host variable - a stray
# machine-wide DEBUG=release or PORT, for example - would otherwise silently
# change how the project behaves. On a shared host there is no such stray
# variable, so the generated .env ships with DOTENV_OVERRIDE=0 and the
# control panel's "Application environment variables" take precedence.
#
# Two passes are needed because the flag itself has to be read out of the file
# first; the first pass never overwrites, the second applies the decision.
load_dotenv(BASE_DIR / ".env", override=False)
_DOTENV_WINS = _truthy(os.getenv("DOTENV_OVERRIDE", "1"))
load_dotenv(BASE_DIR / ".env", override=_DOTENV_WINS)


def env_bool(name: str, default: bool = False) -> bool:
    """Read a conventional boolean value from the environment."""
    return _truthy(os.getenv(name, str(default)))


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment value."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _resolve_secret_key() -> str:
    """Return a stable secret key, generating and persisting one when absent.

    A key supplied through the environment (or .env) always wins. When neither
    is present the key is read from - or written to - `.secret_key` next to the
    project, because shared hosting often offers no shell access and a missing
    key must not take the whole site down. Sessions and signed values then
    survive restarts exactly like an .env-provided key would.
    """
    from_env = os.getenv("SECRET_KEY", "").strip()
    if from_env:
        return from_env

    key_file = BASE_DIR / ".secret_key"
    try:
        stored = key_file.read_text(encoding="utf-8").strip()
    except OSError:
        stored = ""
    if len(stored) >= 32:
        return stored

    generated = get_random_string(
        64, "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"
    )
    try:
        key_file.write_text(generated, encoding="utf-8")
        key_file.chmod(0o600)
    except OSError:
        # A read-only filesystem still boots; the key is simply regenerated on
        # the next start, which only signs every user out once.
        pass
    return generated


SECRET_KEY = _resolve_secret_key()

DEBUG = env_bool("DEBUG")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Provides the built-in sitemap.xml/sitemap_index.xml templates that the
    # sitemap view renders; without it /sitemap.xml raises TemplateDoesNotExist.
    "django.contrib.sitemaps",
    "apps.accounts",
    "apps.store",
    "apps.cart",
    "apps.orders",
    "apps.admin_dashboard",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.NoIndexPrivatePagesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.cart.context_processors.cart_summary",
                "apps.cart.context_processors.footer_categories",
                "apps.core.context_processors.seo",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# SQLite is the single supported database (project spec): a pathlib path
# avoids platform-specific URL parsing pitfalls on Windows. The busy timeout
# matters on shared hosting, where several Passenger worker processes can try
# to write the same file at once - without it they raise "database is locked"
# instead of waiting for the current writer to finish.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": int(os.getenv("SQLITE_TIMEOUT", "20"))},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    # {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    # {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    # {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    # {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Shared hosting (cPanel + Passenger, or any plan without a real web server in
# front of Django) cannot be relied on to serve /static/ and /media/ out of the
# document root, so Django serves them itself. When nginx or Apache already
# handles those prefixes, set SERVE_STATIC_WITH_DJANGO=False - streaming files
# through Python is noticeably slower than letting the web server do it.
SERVE_STATIC_WITH_DJANGO = env_bool("SERVE_STATIC_WITH_DJANGO", True)

# ---------------------------------------------------------------------------
# Django admin theme (django-jazzmin) — gold-on-ink skin that matches the
# storefront. The look lives in static/css/admin_brand.css, loaded through
# JAZZMIN_SETTINGS["custom_css"].
# ---------------------------------------------------------------------------
JAZZMIN_SETTINGS = {
    "site_title": "EXPORT ZONE · Admin",
    "site_header": "EXPORT ZONE",
    "site_brand": "EXPORT ZONE",
    "site_logo": "img/brand-mark.svg",
    "login_logo": "img/brand-lockup.svg",
    "site_logo_classes": "img-circle",
    "site_icon": "img/brand-mark.svg",
    "welcome_sign": "Sign in to the EXPORT ZONE control room",
    "copyright": "EXPORT ZONE · Meherpur, Bangladesh",
    "search_model": ["store.Product", "orders.Order", "accounts.CustomUser"],
    "user_avatar": None,
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index"},
        {"name": "Store console", "url": "admin_dashboard:dashboard"},
        {"name": "Orders", "url": "admin:orders_order_changelist"},
        {"name": "Storefront", "url": "store:home", "new_window": True},
    ],
    "usermenu_links": [
        {"name": "Store console", "url": "admin_dashboard:dashboard", "icon": "fas fa-gauge-high"},
        {"name": "Storefront", "url": "store:home", "new_window": True, "icon": "fas fa-store"},
    ],
    "show_sidebar": True,
    "navigation_expanded": False,
    "order_with_respect_to": ["store", "orders", "accounts", "cart", "auth"],
    "custom_links": {
        "store": [
            {"name": "Storefront", "url": "store:home", "icon": "fas fa-store", "permissions": []},
        ],
        "orders": [
            {
                "name": "Store console",
                "url": "admin_dashboard:dashboard",
                "icon": "fas fa-gauge-high",
                "permissions": [],
            },
        ],
        "cart": [
            {
                "name": "Store console",
                "url": "admin_dashboard:dashboard",
                "icon": "fas fa-gauge-high",
                "permissions": [],
            },
        ],
    },
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "accounts": "fas fa-user-shield",
        "accounts.CustomUser": "fas fa-user-tie",
        "accounts.Address": "fas fa-location-dot",
        "store": "fas fa-store",
        "store.Product": "fas fa-tshirt",
        "store.Category": "fas fa-tags",
        "store.ProductVariant": "fas fa-layer-group",
        "store.ProductImage": "fas fa-images",
        "store.ContactMessage": "fas fa-envelope-open-text",
        "orders": "fas fa-receipt",
        "orders.Order": "fas fa-bag-shopping",
        "orders.OrderItem": "fas fa-box",
        "orders.OrderStatusHistory": "fas fa-clock-rotate-left",
        "cart": "fas fa-cart-shopping",
        "cart.Cart": "fas fa-cart-shopping",
        "cart.CartItem": "fas fa-cart-plus",
    },
    "related_modal_active": True,
    "custom_css": "css/admin_brand.css",
    "custom_js": None,
    "use_google_fonts_cdn": False,
    "show_ui_builder": False,
    "show_theme_chooser": False,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "accounts.customuser": "collapsible",
        "orders.order": "horizontal_tabs",
        "store.product": "horizontal_tabs",
    },
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-warning",
    "navbar": "navbar-dark",
    "no_navbar_border": True,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-warning",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": True,
    "theme": "darkly",
    "default_theme_mode": "dark",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-outline-light",
        "info": "btn-outline-warning btn-sm",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-outline-warning btn-sm",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.CustomUser"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailOrPhoneBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "store:home"
LOGOUT_REDIRECT_URL = "store:home"
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "1209600"))
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))

_configured_email_backend = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
# Django's stock console backend writes through the console codec (cp1252 on
# Windows) and crashes on the taka sign, so local development uses a UTF-8
# writer instead.
if _configured_email_backend == "django.core.mail.backends.console.EmailBackend":
    _configured_email_backend = "apps.core.email_backends.UTF8ConsoleEmailBackend"
# Shared hosts block outbound SMTP to third-party relays, and both senders
# swallow exceptions by design, so a failure would be completely invisible.
# The fallback backend keeps the message in the Passenger log instead.
# Set EMAIL_FALLBACK_TO_CONSOLE=False for a hard failure you would notice.
elif (
    _configured_email_backend == "django.core.mail.backends.smtp.EmailBackend"
    and env_bool("EMAIL_FALLBACK_TO_CONSOLE", True)
):
    _configured_email_backend = "apps.core.email_backends.FallbackSMTPEmailBackend"
EMAIL_BACKEND = _configured_email_backend
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
# Without an explicit timeout a blocked outbound connection hangs until the OS
# gives up, which on a shared host means a request thread is held for minutes.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "15"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EXPORT ZONE <noreply@example.com>")
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# Secure defaults are automatically enabled in production. HTTPS should be
# terminated before Django or configured by the deployment environment.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
# Behind a reverse proxy or load balancer the request scheme has to be read
# from the forwarded header, otherwise SECURE_SSL_REDIRECT can loop forever.
# Turn this on when the host (or Cloudflare) terminates TLS in front of Django.
if env_bool("TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Passenger sends application output to the account's passenger log; a custom
# LOG_FILE is offered for hosts that only expose a file (and the `file` handler
# falls back silently to the console when the path is not writable).
_log_handlers = {"console": {"class": "logging.StreamHandler"}}
_log_file = os.getenv("LOG_FILE", "").strip()
if _log_file:
    _log_handlers["file"] = {
        "class": "logging.FileHandler",
        "filename": _log_file,
        "encoding": "utf-8",
        "delay": True,
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": _log_handlers,
    "root": {"handlers": list(_log_handlers), "level": os.getenv("LOG_LEVEL", "INFO")},
}
