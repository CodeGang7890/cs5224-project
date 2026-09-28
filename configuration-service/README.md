# Configuration Service

Django REST API backend for Ansera Business Admin. It currently contains one app, `configuration_app`, with a single sample endpoint, and uses a local SQLite database.

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

# 4. (Optional) Create an admin user for /admin/
python manage.py createsuperuser

# 5. Start the development server
python manage.py runserver         # http://127.0.0.1:8000
```

To use a different port: `python manage.py runserver 8080`.

When you come back later, you only need to reactivate the virtual environment and start the server:

```bash
source .venv/bin/activate
python manage.py migrate           # safe to re-run; applies any new migrations
python manage.py runserver
```

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
| `python manage.py test` | Runs the tests |
| `python manage.py check` | Checks the project configuration for problems |
| `python manage.py spectacular --validate --file schema.yml` | Exports and validates the OpenAPI schema |

To reset the local database, stop the server, delete `db.sqlite3`, and run `python manage.py migrate` again.

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
├── configuration_app/      # The single Django app
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── serializers.py      # DRF serializers
│   ├── tests.py            # Endpoint + CORS tests
│   ├── urls.py             # App routes, mounted at /api/configuration/
│   └── views.py            # RandomNumberView
├── manage.py
├── requirements.txt
└── .env.example
```

## Adding an endpoint (quick guide)

1. Define a model in `configuration_app/models.py`, then run `python manage.py makemigrations` and `python manage.py migrate`.
2. Add a serializer to `configuration_app/serializers.py`.
3. Create a view or viewset in `configuration_app/views.py`.
4. Register the route in `configuration_app/urls.py`.

The endpoint then appears in Swagger UI at `/api/docs/` automatically.
