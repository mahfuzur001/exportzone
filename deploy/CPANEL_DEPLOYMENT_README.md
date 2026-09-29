# EXPORT ZONE — cPanel Shared Hosting Deployment Guide (SQLite3)

Package: `exportzone-cpanel-production.zip`

This package contains **code only**. It deliberately excludes `db.sqlite3`, `.env`,
`.secret_key` and every other secret, so the production configuration is supplied
entirely through **cPanel environment variables**.

---

## 1. What is inside the ZIP

```
manage.py                 Django entry point
passenger_wsgi.py         Passenger entry point -> config.settings
.htaccess                 Apache hardening
runtime.txt               python-3.10
requirements.txt          5 runtime packages (incl. whitenoise)
config/                   settings.py, urls.py, wsgi.py, asgi.py
apps/                     accounts, admin_dashboard, cart, core, orders, store
templates/                all templates
static/                   source assets
staticfiles/              collectstatic output (223 files + compressed copies)
media/                    uploaded images (1 category image)
tmp/                      Passenger restart marker
```

### Static files are served by WhiteNoise

Following the common cPanel recipe, `whitenoise` is installed and serves
`/static/` from inside the application process:

```python
INSTALLED_APPS = [ ..., "whitenoise.runserver_nostatic", "django.contrib.staticfiles", ... ]
MIDDLEWARE     = [ "django.middleware.security.SecurityMiddleware",
                   "whitenoise.middleware.WhiteNoiseMiddleware", ... ]
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}}
```

Because WhiteNoise now handles `/static/`, set `SERVE_STATIC_WITH_DJANGO=False` so
the project does not *also* register a Django view for that prefix. This is
verified: every asset returns `200` with `Cache-Control: max-age=31536000`.

`/media/` (uploaded product images) is **not** served by WhiteNoise — it only handles
`/static/`.

Because of that, `SERVE_STATIC_WITH_DJANGO` must decide the media route on its
own, otherwise product images break. The settings are arranged so both
configurations work:

| `SERVE_STATIC_WITH_DJANGO` | `/static/` served by | `/media/` served by |
|---|---|---|
| `True` (default) | Django view **and** WhiteNoise — WhiteNoise answers first, so no double work | Django view |
| `False` | WhiteNoise only | **nothing — images 404** |

> **Set `SERVE_STATIC_WITH_DJANGO=True` on cPanel.** WhiteNoise still answers
> `/static/` first because its middleware runs before the URL resolver, so you
> keep the speed while `/media/` keeps working. Verified with `False`: every
> `/static/` asset returns `200` with `Cache-Control: max-age=31536000`.

### Deliberately NOT included

| Excluded | Why |
|---|---|
| `db.sqlite3` | Contains live orders, customers and password hashes. Created on the server by `migrate`. |
| `.env` | Holds your real configuration and credentials. Replaced by cPanel environment variables. |
| `.secret_key` | Your signing key. Supplied as an environment variable instead. |
| `.env.example`, `.env.production.example` | Templates only; they are not needed on the server. |
| `requirements-dev.txt`, `pytest.ini` | Test tooling, never installed in production. |
| Test files, `__pycache__/`, `*.pyc` | Not used at runtime. |
| `.git/`, `.idea/`, `.vscode/`, logs, backups | Development-only. |

---

## 2. How production settings are read

`config/settings.py` was **not modified for this deployment**. It already reads
everything from the environment:

```python
DEBUG               = env_bool("DEBUG")
ALLOWED_HOSTS       = env_list("ALLOWED_HOSTS", ...)
CSRF_TRUSTED_ORIGINS= env_list("CSRF_TRUSTED_ORIGINS")
SECRET_KEY          = _resolve_secret_key()      # env first, then .secret_key
```

Because there is no `.env` in this package, the values come straight from the
process environment, which cPanel populates from the Application environment
variables. This was verified by booting the packaged copy with no `.env` present
and only environment variables set.

**Settings precedence:** if a `.env` file is ever added on the server it will win
unless `DOTENV_OVERRIDE=0` is also set. You do not need it — simply do not upload a
`.env`.

---

## 3. Before you start: generate a SECRET_KEY

The package has no signing key, so you must create one. On your own machine:

```powershell
python -c "import secrets,string;a=string.ascii_letters+string.digits+'!@#$%^&*(-_=+)';print(''.join(secrets.choice(a) for _ in range(64)))"
```

Copy the output. You will paste it into the cPanel environment variables in step 5.

> **Why this matters:** with no `SECRET_KEY`, Django writes a random `.secret_key`

---

## 4. Upload and extract

1. cPanel → **File Manager**.
2. Go to your **home directory** — the folder that *contains* `public_html`
   (usually `/home/youruser/`). **Not inside `public_html`.**
3. **Upload** → choose `exportzone-cpanel-production.zip` → wait for completion.
4. Right-click the ZIP → **Extract** → choose the home directory.

Result: `~/exportzone/manage.py`, `~/exportzone/passenger_wsgi.py`, and so on.

---

## 5. Create the Python App

cPanel → **Software** → **Setup Django App** → **Create Application**

| Field | Value |
|---|---|
| **Application URL** | `yourdomain.com` |
| **Application root** | `exportzone` — relative, **no leading slash** |
| **Deployment method** | **Manual** — *not* "cPanel Dispatch" |
| **Python version** | **3.10** |

Click **Create**.

### Startup file / entry point

| Field | Value |
|---|---|
| **Startup file** | `passenger_wsgi.py` |
| **Entry point** | leave blank — cPanel fills `exportzone/passenger_wsgi.py` |

`passenger_wsgi.py` is already present and already points at `config.settings`,
so no file needs to be created or edited.

---

## 7. Set the environment variables

Application page → **Environment variables**. Add each row (Name → Value):

| Name | Value |
|---|---|
| `DEBUG` | `False` |
| `SECRET_KEY` | the 64-character key from step 3 |
| `ALLOWED_HOSTS` | `yourdomain.com,www.yourdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://yourdomain.com,https://www.yourdomain.com` |
| `SITE_URL` | `https://yourdomain.com` |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_SSL_REDIRECT` | `False` |
| `TRUST_X_FORWARDED_PROTO` | `True` |
| `SECURE_HSTS_SECONDS` | `0` |
| `SQLITE_TIMEOUT` | `20` |
| `SERVE_STATIC_WITH_DJANGO` | `True` — WhiteNoise already serves `/static/`; this keeps the `/media/` route for uploaded images. See section 1. |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | `mail.yourdomain.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | `orders@yourdomain.com` |
| `EMAIL_HOST_PASSWORD` | the mailbox password |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_TIMEOUT` | `15` |
| `EMAIL_FALLBACK_TO_CONSOLE` | `True` |
| `DEFAULT_FROM_EMAIL` | `EXPORT ZONE <orders@yourdomain.com>` |

### Notes on individual values

- **`DEBUG`** must be `False`. With `True`, any error page leaks your file paths
  and settings to the public.
- **`SECURE_SSL_REDIRECT=False` with `TRUST_X_FORWARDED_PROTO=True`** is deliberate.
  cPanel/nginx terminates TLS, so Django only sees the internal `http` hop. If
  redirect were on, visitors would bounce between http and https forever.
- **`SECURE_HSTS_SECONDS=0`** on purpose. Turn it to `31536000` only after HTTPS is
  confirmed working, and never on a host you may still need to reach over http.
- **Cookie flags require a real SSL certificate.** Without one, set
  `SESSION_COOKIE_SECURE=False` and `CSRF_COOKIE_SECURE=False`, otherwise login and
  sessions silently fail.
- **`EMAIL_BACKEND`** — if you skip email for now, set it to
  `django.core.mail.backends.console.EmailBackend` and omit the four `EMAIL_*`

---

## 8. Database configuration (SQLite3)

There is **no** `DATABASE_URL`, no PostgreSQL, no MySQL. The project is
SQLite-only and needs nothing configured:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": int(os.getenv("SQLITE_TIMEOUT", "20"))},
    }
}
```

- The database file is `db.sqlite3`, created beside `manage.py`.
- **It is not in the ZIP by design** — it would expose real customers and password
  hashes. Step 9 creates a fresh one.
- `SQLITE_TIMEOUT=20` makes SQLite wait up to 20 seconds for a lock instead of
  raising "database is locked", which is what several Passenger workers would
  otherwise cause.

---

## 9. Run the migrations

Open **cPanel → Terminal** (or SSH). Use the virtualenv path cPanel showed you.

```bash
cd ~/exportzone
../virtualenv/exportzone/3.10/bin/python manage.py migrate
```

Expected output lists each migration as `OK`. This creates `db.sqlite3` with all
tables.

You should see **29 migrations** applied — matching the development database. If
you only see the Django built-ins (`admin`, `auth`, `contenttypes`, `sessions`)
and none of your own apps, see the note below.

> ### Why this package ships four extra files
>
> The four apps in this project have their `migrations/` folders without an
> `__init__.py` marker. Django therefore ignores those folders entirely and
> `showmigrations` reports "(no migrations)" — the tables only exist because the
> development `db.sqlite3` was already migrated.
>
> Since this package ships **no database**, `migrate` would create only the Django
> built-in tables and your site would then fail with
> `OperationalError: no such table: store_product`.
>
> To avoid that without touching the source project, the package adds the missing
> markers at these four paths. They are empty files and change no logic:
>
> ```
> apps/accounts/migrations/__init__.py
> apps/cart/migrations/__init__.py
> apps/orders/migrations/__init__.py
> apps/store/migrations/__init__.py
> ```
>
> With them in place `migrate` applies all 29 migrations. **The same four files
> should be added to the source project** so local and production behaviour match;
> that is left to you because it changes the project itself.

**Safe rules**
- `migrate` only **adds** tables and columns; it never deletes data.
- **Never** run `manage.py flush` or `migrate --run-syncdb`. `flush` empties every
  table, including your orders and customers.

---

## 10. Load the demo catalogue (optional)

The database starts empty. To create the seven categories, ten products and their
stock variants:

```bash
../virtualenv/exportzone/3.10/bin/python manage.py seed_data
```

It is idempotent — running it twice is safe. To start with a genuinely empty shop
instead, just skip this step and add categories and products from `/admin/`.

---

## 11. Create a superuser

```bash
../virtualenv/exportzone/3.10/bin/python manage.py createsuperuser

---

## 13. Set permissions

The web user must be able to **read** the code and **write** the database, uploads
and restart marker.

```bash
chmod 755 ~/exportzone
chmod 700 ~/exportzone/db.sqlite3
chmod 755 ~/exportzone/db.sqlite3        # after migrate creates it
chmod 755 ~/exportzone/media
chmod 755 ~/exportzone/staticfiles
chmod 777 ~/exportzone/tmp               # Passenger writes restart.txt here
```

If `collectstatic` or `migrate` reports a permission error, fix it with:

```bash
cd ~/exportzone
find . -type d -exec chmod 755 {} \;
find . -type f -exec chmod 644 {} \;
chmod 666 db.sqlite3
chmod 777 tmp
```

---

## 14. Restart Passenger

Whenever you change an environment variable, `.htaccess` or any Python file:

```bash
cd ~/exportzone
touch tmp/restart.txt
```

The application page also has a **Restart** button — either works.

Passenger keeps worker processes alive with the settings they started with, so
without a restart your new environment variables appear to be ignored.

---

## 15. Verify the deployment

| Check | Expected |
|---|---|
| `https://yourdomain.com/` | Storefront loads, `DEBUG=False` |
| `/shop/` | Product list renders |
| `/admin/` | Admin login page, jazzmin theme |
| `/admin-dashboard/` | Redirects to login when signed out |
| Place one order | Stock decreases, confirmation page appears |
| `/robots.txt`, `/sitemap.xml` | Both return 200 |

Confirm `DEBUG` is really off by triggering a missing page: `/no-such-page/` must
show your branded `404.html`, **not** Django's technical error page.

---

## 16. If you get HTTP 500

1. **cPanel → Errors** — the real traceback is at the bottom of the log.
2. **`SECRET_KEY` missing** — the single most common cause. Without it Django
   regenerates a key on every request and login breaks.
3. **`ALLOWED_HOSTS` wrong** — a mismatch returns HTTP 400, not 500.
4. **Permissions** — re-apply step 13.
5. **Virtualenv path** — copy the exact path from the application page; the
   `../virtualenv/...` above is a convention.
6. **Restart Passenger** after every change (step 14).

---

## 17. Updating later

This package contains **no database and no `.env`**, so uploading it again is
always safe: it can never overwrite `db.sqlite3`, uploaded images or your
environment variables.

```bash
# back up first
cp ~/exportzone/db.sqlite3 ~/db-backup-$(date +%F).sqlite3
```

Upload the new ZIP, overwrite the code files, then:

```bash
cd ~/exportzone
../virtualenv/exportzone/3.10/bin/python manage.py migrate
touch tmp/restart.txt
```

---

## 18. Quick checklist

- [ ] `SECRET_KEY` generated (64 chars)
- [ ] SSL certificate installed (cPanel → SSL/TLS Status)
- [ ] ZIP uploaded to home directory, extracted to `~/exportzone/`
- [ ] Python App created — root `exportzone` (no slash), method **Manual**, Python **3.10**
- [ ] Startup file `passenger_wsgi.py`
- [ ] **Run Upgrade** pressed
- [ ] All environment variables added, `DEBUG=False`
- [ ] `manage.py migrate` run — `db.sqlite3` created
- [ ] `manage.py seed_data` run (optional demo catalogue)
- [ ] `manage.py createsuperuser` run
- [ ] Permissions applied
- [ ] `touch tmp/restart.txt`
- [ ] Site loads and `/admin/` login works
- [ ] Test order placed, stock decreases

```

It prompts for username, email and password. Use a strong password.

Then open `https://yourdomain.com/admin/`. The admin is themed to match the
storefront (django-jazzmin), and a **Store console** link opens the staff-only
dashboard at `/admin-dashboard/`.

---

## 12. Run collectstatic

The package already ships a complete `staticfiles/` (223 files), so this step is a
safety net. Run it after any change to `static/` or to a CSS/JS file:

```bash
cd ~/exportzone
../virtualenv/exportzone/3.10/bin/python manage.py collectstatic --noinput
```

- `--noinput` suppresses the confirmation prompt.
- `staticfiles/` must be writable. On a permission error, delete the folder and
  re-run, or fix ownership (step 13).
- The site serves `/static/` and `/media/` through Django itself
  (`SERVE_STATIC_WITH_DJANGO=True`), which is the reliable option on shared
  hosting. Even a failed collectstatic leaves the site working with the bundled copy.

  credentials. Mail is then written to the Passenger log instead of being sent.


---

## 6. Install the requirements

On the application page press **Run Upgrade**. cPanel reads `requirements.txt` and
installs into its virtualenv:

```
Django>=5.2,<6.0
django-jazzmin>=3.0,<4.0
Pillow>=11.0,<12.0
python-dotenv>=1.0,<2.0
whitenoise>=6.9,<7.0
```

Confirm it worked — the green *Dependencies installed* message appears and a
virtualenv path is shown, e.g. `~/virtualenv/exportzone/3.10`. You need that path
for the remaining commands.

> If you prefer to paste requirements by hand, this box in cPanel
> ("Enter your requirements") accepts the same five lines. Pressing *Run Pip
> Install* twice is a known cPanel quirk — if the first attempt reports an
> error, just run it again.

> file on the first request. On shared hosting that file often cannot be written,
> so the key is regenerated on every request — which signs every user out
> immediately and breaks login. Always set `SECRET_KEY` yourself.
