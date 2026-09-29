# EXPORT ZONE

Premium clothing e-commerce for Meherpur, Bangladesh, built as a server-rendered Django application. The project ships a complete storefront: catalog, cart, cash-on-delivery checkout, customer account self-service, password-reset and password-change flows, contact messaging, an admin dashboard, and order management.

## Technology

- Python 3.10+ and Django 5.2 (the shared host runs the version pinned in `exportzone/runtime.txt`)
- Django templates with Tailwind CSS and progressive vanilla JavaScript (no React, no REST API)
- SQLite as the single supported database
- Pillow for images and python-dotenv for environment configuration
- Django's built-in test runner, plus optional pytest / pytest-django

## Local setup

```powershell
# from the repository root
cd exportzone
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

`requirements.txt` carries the four runtime packages only. Install the test
tooling with `pip install -r requirements-dev.txt` when you need pytest.

Set a unique `SECRET_KEY` in `exportzone/.env`; it must never be committed. Local email is printed to the console. The home page is available at `http://127.0.0.1:8000/`.

Optional demo catalog (idempotent — safe to run repeatedly):

```powershell
cd exportzone
python manage.py seed_data
```

`seed_data` creates the seven spec categories (Jeans, Shirts, Polo T-Shirts, T-Shirts, Chinos, Jackets, Accessories), realistic products for each, and stock variants (waist sizes 28–42 for denim, S–XXL for tops; colors Black, Blue, Navy, White, Gray, Beige, Green). It creates no user accounts and no fake reviews.

## Verification

```powershell
cd exportzone
python manage.py check
python manage.py test          # full Django test suite
pytest                         # optional; uses pytest.ini
```

## Feature highlights

- **Storefront:** home with featured/new arrivals, shop with category/size/color/price filters, free-text search, 5 sort modes and pagination; product pages with stock-aware variant pickers and related products.
- **Navigation (spec §22):** desktop and mobile menus show Home, dynamic category links (ordered Jeans → Shirts → Polo T-Shirts → T-Shirts first), New Arrivals, Collections, About, Contact, plus search/account/cart icons with a live cart badge.
- **Cart:** variant-level quantities, owner-scoped update/remove, Clear-cart action with confirmation, empty states, header count badge.
- **Checkout:** cash on delivery only (bKash/Nagad shown as Coming Soon), saved-address picker that fills the delivery form, double-submit guard, `transaction.atomic()` + `select_for_update()` order creation with stock decrement, order numbers `EZ-YYYYMMDD-XXXX`, confirmation page.
- **Account:** register + expiring email-verification links, email-or-phone login, remember-me, forgot/reset password (`/forgot-password/`, `/reset-password/<uidb64>/<token>/`), profile with recent orders, saved address book (add/edit/delete/set default) and change-password (session preserved).
- **Orders:** paginated history at `/account/orders/`, detail view, cancel while pending, staff-only admin dashboard with stats, low-stock alerts and customer/order/product/category management.
- **Contact:** validated form persisted to the `ContactMessage` model, manageable in Django admin.
- **Errors:** branded `templates/404.html`, `403.html`, `500.html`.
- **Seed data:** `python manage.py seed_data` (idempotent; 7 spec categories, realistic products, sizes 28–42 + S–XXL, colors Black/Blue/Navy/White/Gray/Beige/Green; no fake users or reviews).

## URL map (spec §42)

| Page | Path |
| --- | --- |
| Home / Shop / Product / About / Contact | `/`, `/shop/`, `/product/<slug>/`, `/about/`, `/contact/` |
| Cart / Checkout / Success | `/cart/`, `/checkout/`, `/order-success/<order_number>/` |
| Orders | `/account/orders/` (+ detail, + cancel) |
| Register / Login / Logout | `/register/`, `/login/`, `/logout/` |
| Verification | `/verify-email/<uidb64>/<token>/`, `/verify-email/sent/`, `/verify-email/success/` |
| Password reset | `/forgot-password/`, `/reset-password/<uidb64>/<token>/` |
| Account / Addresses / Password | `/account/`, `/account/addresses/`, `/account/password/` |
| Admin | `/admin/`, `/admin-dashboard/` |

URL namespaces are unchanged (`store`, `cart`, `orders`, `accounts`); templates and tests always reverse names.

## Project layout

```text
exportzone/
├── config/             # settings (SQLite-only) + root URLs
├── apps/
│   ├── core/           # shared static pages
│   ├── accounts/       # custom user, address book, auth flows
│   ├── store/          # catalog, contact form, seed_data command
│   ├── cart/           # cart models, services, context processors
│   ├── orders/         # checkout + atomic order creation
│   └── admin_dashboard/# staff-only ops dashboard
├── templates/          # base layout, pages, emails, error templates
├── static/             # CSS, site.js, images
└── tests/              # cross-app suite + URL audit
```

## Deploying to shared hosting (cPanel / Passenger)

```powershell
# from the repository root
.\deploy\backup_data.ps1                                                  # always back up first
.\deploy\build_shared_hosting_package.ps1 -Domain example.com -SkipData   # every update
```

`build_shared_hosting_package.ps1` runs `collectstatic`, copies only the code the
host needs, writes a fresh `SECRET_KEY` plus a production `.env`, and zips the
result into `dist/`.

**`-SkipData` is the important flag.** Without it the package contains
`db.sqlite3` and `media/`, and uploading it would overwrite the live orders,
customers and uploaded images. With it, both are left out — the server keeps
its own copies and only the code is replaced. Use it for every update after
the initial deploy.

Pass `-NoSsl` for the first upload if the host has no certificate yet; otherwise
`SECURE_SSL_REDIRECT` turns the whole site into a redirect loop. Pass
`-EmailHost`/`-EmailUser`/`-EmailPassword` to enable real SMTP.

The full cPanel walkthrough, the `Application root` value to use, and a
troubleshooting table live in **[deploy/SHARED_HOSTING_DEPLOY.md](deploy/SHARED_HOSTING_DEPLOY.md)**.

## Production notes

Set `DEBUG=False`, restrict `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, configure SMTP credentials, run `python manage.py collectstatic`, and serve static/media through the platform. SQLite (`exportzone/db.sqlite3`) is the only supported database — back it up regularly. Security-cookie and HSTS defaults activate automatically when debug mode is disabled.

`.env` is the single source of configuration. By default it wins over real environment variables, so a stray machine-wide `DEBUG` or `PORT` cannot change how the project behaves; set `DOTENV_OVERRIDE=0` (as the deploy script does) to let cPanel's "Application environment variables" take precedence instead. If `SECRET_KEY` is missing entirely, one is generated and persisted to `exportzone/.secret_key` so a host without shell access can still boot.