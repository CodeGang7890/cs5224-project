# Configuration Service

Django REST API backend for Ansera Business Admin. It has three Django apps: `configuration_app`, `auth_app` and `product_app`. So far they contain the data models, Django Admin screens, sample fixtures and one sample endpoint. It uses a local SQLite database for now.

## Tech stack

| Concern | Library |
| --- | --- |
| Web framework | [Django](https://www.djangoproject.com/) 6.1 |
| REST APIs | [Django REST Framework (DRF)](https://www.django-rest-framework.org/) |
| Swagger / OpenAPI docs | [drf-spectacular](https://drf-spectacular.readthedocs.io/) (OpenAPI 3, Swagger UI + ReDoc) |
| CORS | [django-cors-headers](https://github.com/adamchainz/django-cors-headers) |
| Database | SQLite (local file `db.sqlite3`); a real database will be integrated later |

## Prerequisites

- **Python 3.12+** (required by Django 6.1). Check with `python3 --version`.

## Getting started

Run all commands from the `configuration-service/` folder.

```bash
cd configuration-service

# 1. Create and activate a virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply database migrations (creates db.sqlite3 on first run)
python manage.py migrate

# 4. Load sample data (businesses, business users, products, FAQs)
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs

# 5. Create the local admin superuser (username: superuser, password: 123)
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com

# 6. Start the development server
python manage.py runserver         # http://127.0.0.1:8000
```

Then log in to Django Admin at <http://127.0.0.1:8000/admin/> with **`superuser` / `123`**. The superuser can view, add, edit and delete everything.

> [!WARNING]
> `superuser` / `123` is a throwaway login for local development only. Never create it on a shared or deployed database. `--noinput` skips Django's password-strength checks, which is why the command accepts such a short password. On Windows (PowerShell), run `$env:DJANGO_SUPERUSER_PASSWORD="123"` first, then run the `createsuperuser` command without the `DJANGO_SUPERUSER_PASSWORD=123` prefix.

To use a different port: `python manage.py runserver 8080`.

When you come back later, you only need to reactivate the virtual environment and start the server:

```bash
source .venv/bin/activate
python manage.py migrate           # safe to re-run; applies any new migrations
python manage.py runserver
```

## Sample data (fixtures)

The fixtures are JSON files in each app's `fixtures/` folder. Load them all with:

```bash
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs
```

| Fixture | File | Contents |
| --- | --- | --- |
| `sample_business_configurations` | `configuration_app/fixtures/` | 3 businesses: Kopi & Co. Café, Bloom Florist Studio, FitLab Personal Training |
| `sample_business_users` | `auth_app/fixtures/` | 4 business users linked to those businesses |
| `sample_products` | `product_app/fixtures/` | 8 products (one of them inactive) |
| `sample_faqs` | `product_app/fixtures/` | 6 FAQs |

The sample business users are `kopi_owner`, `bloom_owner`, `bloom_staff` and `fitlab_owner`. They all have the password `password123` and aren't staff, so they can't log in to Django Admin.

Notes:
- Fixtures use fixed IDs, so re-running `loaddata` resets those records to the sample values rather than creating duplicates. Records you created yourself are kept.
- Load them in one command, as shown above. The records depend on each other: users, products and FAQs point to businesses.
- `loaddata` saves records as-is, without running model validation. When you edit a fixture, keep the data within the model rules.

## Data model

| App | Model | Fields |
| --- | --- | --- |
| `configuration_app` | `BusinessConfiguration` | `id`, `business_name` (≤150 chars), `description` (≤2,000 chars, optional), `location` (≤255 chars) |
| `auth_app` | `BusinessUser` | Every field of Django's built-in user (username, password, email, first/last name, `is_staff`, `is_superuser`, `is_active`, groups, permissions, `last_login`, `date_joined`), plus `business` → `BusinessConfiguration` (optional) |
| `product_app` | `Product` | `id`, `business` → `BusinessConfiguration`, `name` (≤150 chars), `description` (≤5,000 chars, optional), `price` (≥0, 2 decimal places, up to 99,999,999.99), `quantity_available` / `quantity_on_hold` / `quantity_sold` (whole numbers ≥0, default 0), `is_active` (default true) |
| `product_app` | `FAQ` | `id`, `business` → `BusinessConfiguration`, `question` (≤300 chars), `answer` (≤10,000 chars) |

Rules enforced by Django validation (e.g. in Django Admin) **and** by the database:
- Price and quantities can't be negative.
- Business names, locations, product names, FAQ questions and FAQ answers can't be empty.
- Product names and FAQ questions must be unique **within a business**. Different businesses can reuse them.

When a business is deleted:
- Its **products and FAQs are deleted** with it.
- Its **users are kept**, with their business link cleared.

`BusinessUser` is the project's user model (`AUTH_USER_MODEL = 'auth_app.BusinessUser'`). In code, refer to it with `django.contrib.auth.get_user_model()` or `settings.AUTH_USER_MODEL`.

## Useful URLs (once the server is running)

| URL | What it is |
| --- | --- |
| <http://127.0.0.1:8000/api/docs/> | Swagger UI (interactive API docs) |
| <http://127.0.0.1:8000/api/redoc/> | ReDoc (alternative API docs) |
| <http://127.0.0.1:8000/api/schema/> | Raw OpenAPI 3 schema (YAML; add `?format=json` for JSON) |
| <http://127.0.0.1:8000/admin/> | Django admin |
| <http://127.0.0.1:8000/api/configuration/random-number/> | Sample endpoint: returns `{"value": <1–10>}`. `frontend-app`'s Home tab calls it. |

## Common commands

| Command | What it does |
| --- | --- |
| `python manage.py runserver` | Starts the dev server with auto-reload |
| `python manage.py makemigrations` | Creates migration files after you change models |
| `python manage.py migrate` | Applies migrations to the database |
| `python manage.py createsuperuser` | Creates an admin user |
| `python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs` | Loads the sample data |
| `python manage.py test` | Runs the tests |
| `python manage.py check` | Checks the project configuration for problems |
| `python manage.py spectacular --validate --file schema.yml` | Exports and validates the OpenAPI schema |

### Resetting the local database

To wipe everything and start fresh with sample data:

```bash
rm db.sqlite3
python manage.py migrate
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com
```

> [!IMPORTANT]
> If your `db.sqlite3` was created before the custom user model (`BusinessUser`) was added, `migrate` fails with an `InconsistentMigrationHistory` error. Reset the database as shown above.

## Configuration (environment variables)

`config/settings.py` reads the variables below. The defaults work for local development, so you don't need to set anything to get started. See `.env.example` for a template. The file isn't loaded automatically; export the variables in your shell, for example `export DJANGO_DEBUG=False`.

| Variable | Default | Description |
| --- | --- | --- |
| `DJANGO_DEBUG` | `True` | Debug mode. Set to `False` outside local development. |
| `DJANGO_SECRET_KEY` | insecure dev key (only when `DEBUG` is on) | Must be set when `DEBUG` is off. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames the server responds to. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated origins allowed to call the API from a browser. The default is the `frontend-app` Vite dev server. |

## Connecting from frontend-app

`frontend-app` (Vite, <http://localhost:5173>) calls this service from the browser, so CORS must allow its origin:

- `corsheaders.middleware.CorsMiddleware` is the **first** entry in `MIDDLEWARE`. That way every response, including redirects and errors produced by later middleware, carries CORS headers.
- `CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173` and `http://127.0.0.1:5173`. For other frontend URLs (e.g. a deployed site), set `DJANGO_CORS_ALLOWED_ORIGINS`.
- `CORS_URLS_REGEX` limits CORS headers to `/api/` routes.

To try it, run `python manage.py runserver` here and `npm run dev` in `../frontend-app`, then open <http://localhost:5173>.

## Project structure

```
configuration-service/
├── config/                 # Django project: settings, root URLs, WSGI/ASGI entry points
│   ├── settings.py
│   ├── urls.py             # /admin, /api/configuration, /api/schema, /api/docs, /api/redoc
│   ├── asgi.py
│   └── wsgi.py
├── configuration_app/      # Businesses (BusinessConfiguration) + sample API
│   ├── fixtures/           # sample_business_configurations.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py
│   ├── serializers.py      # DRF serializers
│   ├── tests.py            # Endpoint, CORS and model tests
│   ├── urls.py             # App routes, mounted at /api/configuration/
│   └── views.py            # RandomNumberView
├── auth_app/               # Custom user model (BusinessUser)
│   ├── fixtures/           # sample_business_users.json
│   ├── migrations/
│   ├── admin.py            # BusinessUserAdmin (extends Django's UserAdmin)
│   ├── models.py
│   └── tests.py            # Model + admin smoke tests
├── product_app/            # Products and FAQs
│   ├── fixtures/           # sample_products.json, sample_faqs.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py
│   └── tests.py            # Validation tests
├── manage.py
├── requirements.txt
└── .env.example
```

## Adding an endpoint (quick guide)

1. Define a model in the right app's `models.py`, then run `python manage.py makemigrations` and `python manage.py migrate`.
2. Add a serializer to the app's `serializers.py`.
3. Create a view or viewset in the app's `views.py`.
4. Register the route in the app's `urls.py`. For a new app, also `include()` its URLs in `config/urls.py` under `/api/`.

The endpoint then appears in Swagger UI at `/api/docs/` automatically.
