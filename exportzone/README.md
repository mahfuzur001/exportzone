# EXPORT ZONE

Premium clothing e-commerce for Meherpur, Bangladesh, built as a server-rendered Django application. The current delivery includes the secure project foundation and a dark, gold premium authentication experience; catalog and commerce features are delivered in subsequent phases.

## Technology

- Python 3.12+ and Django 5
- Django templates, Tailwind CSS, and progressive vanilla JavaScript
- SQLite for local development; PostgreSQL through `DATABASE_URL` in production
- django-jazzmin for the branded Django admin console at `/admin/`
- Pillow for product images and python-dotenv for environment configuration

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Set a unique `SECRET_KEY` in `.env`; it must never be committed. Local email is printed to the console through a UTF-8 console backend (`apps/core/email_backends.py`), because Windows consoles are cp1252 and Django's stock console backend crashes on the taka sign (৳). The home page is available at `http://127.0.0.1:8000/`.

## Verification

```powershell
python manage.py check
python manage.py test
```

## Current authentication features

- Custom user model with unique email and Bangladesh phone number
- Registration with server-side validation and terms acceptance, activating the account immediately
- Branded "account created" welcome email on every successful registration (no email-verification step)
- Email-or-phone login with a working Show/Hide password toggle, secure session handling, and optional Remember Me; staff accounts land in the `/admin-dashboard/` operations console, customers keep the storefront and any explicit `?next=` target always wins
- Django's built-in secure password-reset flow with branded email templates
- Login-protected profile page and customized Django user administration

Authentication routes live under `/accounts/`: `register/`, `login/`, `password-reset/`, and the authenticated account page at `/accounts/`.
## Admin console

Two consoles ship with the project:

- **Store console** at `/admin-dashboard/` — the day-to-day operations UI (orders, products, categories, customers, low stock), restricted to staff accounts.
- **Django console** at `/admin/` — the full model administration, themed with django-jazzmin to match the storefront. `JAZZMIN_SETTINGS` and `JAZZMIN_UI_TWEAKS` in `config/settings.py` hold the branding (site title, gold-on-ink palette, Font Awesome icons per app/model, dark "darkly" Bootswatch theme, top menu links to both consoles and the storefront), while `static/css/admin_brand.css` carries the colour, typography (Inter + Playfair Display), table, button, form, and login-card styling. `static/img/brand-mark.svg` and `static/img/brand-lockup.svg` provide the sidebar mark and the login wordmark. Order statuses can be moved here too: the order change form offers a **dropdown limited to the valid next steps** (plus an optional status note), every change is written to the read-only status-history inline on the same page, the customer gets the usual status email, and the orders changelist carries bulk actions ("Mark selected orders as Confirmed / Processing / Shipped / Delivered / Cancelled") that skip orders which cannot legally move and report them.



## Project layout

```text
exportzone/
├── config/             # Environment-driven Django configuration
├── apps/
│   ├── core/           # Shared pages and storefront foundation
│   ├── accounts/       # Authentication (Phase 2)
│   ├── store/          # Catalog (Phase 4)
│   ├── cart/           # Cart (Phase 7)
│   └── orders/         # Checkout and order creation (Phase 8+)
├── templates/          # Base, component, email, and page templates
├── static/             # Source CSS, JavaScript, and images
├── media/              # Local user-uploaded media (not committed)
└── tests/              # Automated tests
```

## Production notes

Use a PostgreSQL `DATABASE_URL`, set `DEBUG=False`, restrict `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, use SMTP credentials from the deployment environment, run `collectstatic`, and serve static/media files through the deployment platform. Leave `DATABASE_URL` blank locally to use the path-safe SQLite database. The security-cookie and HSTS defaults activate when debug mode is disabled.

Future project commands will include `seed_data` and the standard `createsuperuser` command once the relevant models are introduced.
