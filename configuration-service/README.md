# Configuration Service

Django REST API backend for Ansera Business Admin. It has four Django apps: `configuration_app`, `auth_app`, `product_app` and `chat_app`. So far they contain the data models, Django Admin screens, sample fixtures, CRUD APIs for products and FAQs, a chat endpoint backed by a local LLM (Ollama), and one sample endpoint. It uses a local SQLite database for now.

## Tech stack

| Concern | Library |
| --- | --- |
| Web framework | [Django](https://www.djangoproject.com/) 6.1 |
| REST APIs | [Django REST Framework (DRF)](https://www.django-rest-framework.org/) |
| Swagger / OpenAPI docs | [drf-spectacular](https://drf-spectacular.readthedocs.io/) (OpenAPI 3, Swagger UI + ReDoc) |
| CORS | [django-cors-headers](https://github.com/adamchainz/django-cors-headers) |
| Authentication | [djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/) (JWT access/refresh tokens) |
| LLM (chat) | [ollama](https://github.com/ollama/ollama-python) Python client, talking to a local [Ollama](https://ollama.com/) server |
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
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions

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
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions
```

| Fixture | File | Contents |
| --- | --- | --- |
| `sample_business_configurations` | `configuration_app/fixtures/` | 3 businesses: Kopi & Co. Café, Bloom Florist Studio, FitLab Personal Training |
| `sample_business_users` | `auth_app/fixtures/` | 4 business users linked to those businesses |
| `sample_products` | `product_app/fixtures/` | 8 products (one of them inactive) |
| `sample_faqs` | `product_app/fixtures/` | 6 FAQs |
| `sample_chat_configurations` | `chat_app/fixtures/` | 1 chat flow for Kopi & Co. Café: start → product selection → details collection → confirmation |
| `sample_chat_sessions` | `chat_app/fixtures/` | 6 customer chats: 3 with Kopi & Co. Café (at different steps of its flow), 2 with Bloom Florist Studio, 1 with FitLab. `+6591234567` chats with both the café and the florist |

Every sample account uses the password **`123`**, so you can log in as anyone while testing:

| Username | Business | Can log in to |
| --- | --- | --- |
| `kopi_owner` | Kopi & Co. Café (1) | API only |
| `bloom_owner` | Bloom Florist Studio (2) | API only |
| `bloom_staff` | Bloom Florist Studio (2) | API only |
| `fitlab_owner` | FitLab Personal Training (3) | API only |
| `superuser` (created by the `createsuperuser` command, not a fixture) | none | Django Admin (full access). Gets 403 on product/FAQ changes, because it has no business. |

Business users aren't staff, so they can't log in to Django Admin.

Notes:
- Fixtures use fixed IDs, so re-running `loaddata` resets those records to the sample values rather than creating duplicates. Records you created yourself are kept.
- Load them in one command, as shown above. The records depend on each other: users, products, FAQs, chat configurations and chat sessions point to businesses, and chat sessions' `chat_state_id` points to a block in the business's chat configuration.
- `loaddata` saves records as-is, without running model validation. When you edit a fixture, keep the data within the model rules.

## Data model

| App | Model | Fields |
| --- | --- | --- |
| `configuration_app` | `BusinessConfiguration` | `id`, `business_name` (≤150 chars), `description` (≤2,000 chars, optional), `location` (≤255 chars) |
| `auth_app` | `BusinessUser` | Every field of Django's built-in user (username, password, email, first/last name, `is_staff`, `is_superuser`, `is_active`, groups, permissions, `last_login`, `date_joined`), plus `business` → `BusinessConfiguration` (optional) |
| `product_app` | `Product` | `id`, `business` → `BusinessConfiguration`, `name` (≤150 chars), `description` (≤5,000 chars, optional), `price` (≥0, 2 decimal places, up to 99,999,999.99), `quantity_available` / `quantity_on_hold` / `quantity_sold` (whole numbers ≥0, default 0), `is_active` (default true) |
| `product_app` | `FAQ` | `id`, `business` → `BusinessConfiguration`, `question` (≤300 chars), `answer` (≤10,000 chars) |
| `chat_app` | `ChatSession` | `id`, `business` → `BusinessConfiguration`, `phone_number` (the customer's, international format e.g. `+6591234567`), `display_name` (≤150 chars, optional), `created_time` (set automatically), `last_chat_time`, `chat_message_json` (the conversation, see below), `chat_state_id` (the flow block the customer is at, or empty) |
| `chat_app` | `ChatConfiguration` | `id`, `business` → `BusinessConfiguration` (one per business), `config_json` (the chat flow, see below), `last_updated` (set automatically on every save) |

Rules enforced by Django validation (e.g. in Django Admin) **and** by the database:
- Price and quantities can't be negative.
- Business names, locations, product names, FAQ questions and FAQ answers can't be empty.
- Product names and FAQ questions must be unique **within a business**. Different businesses can reuse them.

`ChatConfiguration.config_json` is a list of blocks, e.g. `{"id": 1, "next_block_id": 2, "block_type": "START_BLOCK", "position_x": 100, "position_y": 100}`. `chat_app/validators.py` (`validate_chat_config`) checks it on every validated save, e.g. in Django Admin:
- Every block has exactly those five fields.
- `id` is an integer or a non-blank string (e.g. a UUID), unique within the list.
- `next_block_id` is `null` or the `id` of another block in the list.
- `block_type` is one of `START_BLOCK`, `PRODUCT_SELECTION_BLOCK`, `DETAILS_COLLECTION_BLOCK`, `CONFIRMATION_BLOCK` (defined in `chat_app/constants.py`). There must be exactly one `START_BLOCK`; other types can repeat.
- `position_x` / `position_y` are numbers.

`ChatSession` rules (checked by Django validation, e.g. in Django Admin):
- `phone_number` is unique **within a business** (also enforced by the database). Different businesses can each have a chat with the same number.
- `chat_message_json` is a list of messages, oldest first: `{"message": "Hi", "sent_by": "customer", "message_time": "2026-09-01T09:00:00+08:00"}`. `validate_chat_messages` (`chat_app/validators.py`) checks that `message` is non-blank (≤4,096 chars), `sent_by` is `customer`, `business-manual` or `business-automated` (defined in `chat_app/constants.py`), and `message_time` is an ISO 8601 date-time with a timezone, in chronological order. An empty list is fine.
- `chat_state_id` is empty, or the `id` of a block in the business's chat configuration (the type must match too: `"2"` is not block `2`). If the business has no chat configuration, it must be empty.

When a business is deleted:
- Its **products, FAQs, chat configuration and chat sessions are deleted** with it.
- Its **users are kept**, with their business link cleared.

`BusinessUser` is the project's user model (`AUTH_USER_MODEL = 'auth_app.BusinessUser'`). In code, refer to it with `django.contrib.auth.get_user_model()` or `settings.AUTH_USER_MODEL`.

## APIs

### Authentication (JWT)

| Method | URL | Body → response | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/auth/token/` | `{username, password}` → `{access, refresh}` | Log in |
| `POST` | `/api/auth/token/refresh/` | `{refresh}` → `{access, refresh}` | Get a new access token. The refresh token also rotates: use the new one, because the old one is now invalid. |
| `POST` | `/api/auth/token/verify/` | `{token}` → `{}` | Check that a token is valid (200) or not (401) |
| `POST` | `/api/auth/logout/` | `{refresh}` → `{}` | Log out: revokes (blacklists) the refresh token |
| `GET` | `/api/auth/me/` | → profile | Your profile: `id`, `username`, `email`, `first_name`, `last_name`, **`business`** (your `BusinessConfiguration` ID, or `null`), `business_name`, `is_staff`, `is_superuser`. Requires login. |

- **Access token:** send it as `Authorization: Bearer <access>`. It's valid for **15 minutes**.
- **Refresh token:** valid for **7 days**. It can be used only once, because each refresh returns a new one.
- **Settings:** lifetimes and rotation are configured in `SIMPLE_JWT` in `config/settings.py`.
- **Endpoint access:** the login, refresh, verify and logout endpoints are public; `me/` needs a login.

### Products and FAQs

All of these require you to be logged in.

| Method | URL | What it does |
| --- | --- | --- |
| `GET` | `/api/products/` | List your business's products (paginated, 20 per page: `?page=2`) |
| `POST` | `/api/products/` | Create a product |
| `GET` | `/api/products/{id}/` | Get a product |
| `PUT` / `PATCH` | `/api/products/{id}/` | Replace / partially update a product |
| `DELETE` | `/api/products/{id}/` | Delete a product |
| `GET` / `POST` | `/api/faqs/` | List / create FAQs |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/faqs/{id}/` | Get / replace / update / delete an FAQ |
| `GET` | `/api/businesses/{business_id}/products/` | List **all** products of a business, including inactive ones (paginated) |
| `GET` | `/api/businesses/{business_id}/faqs/` | List all FAQs of a business (paginated) |
| `GET` | `/api/configuration/random-number/` | Sample endpoint (public, no login needed) |
| `POST` | `/api/chat/` | `{prompt}` → `{reply, model, options}`: one-off chat with the local LLM (public, no login needed) |
| `GET` | `/api/chat/configuration/` | Your business's chat configuration `{id, business, config_json, last_updated}`. 404 if it has none yet |
| `PUT` | `/api/chat/configuration/` | `{config_json}`: replace your business's chat flow (validated). Creates it (201) if missing, otherwise 200 |

### Chat (temporary)

`chat_app` is a temporary copy of `../messaging-service`'s `/chat` endpoint, living here until that service has its own database. It needs [Ollama](https://ollama.com/) running on `http://localhost:11434` with the model pulled (`ollama pull qwen2.5:7b-instruct-q4_K_M`).

- Every request is independent: the fixed system prompt plus your `prompt` (≤4,000 characters). No history is kept.
- The model, system prompt and sampling options (`seed`, `temperature`, `num_predict` (max tokens), `top_k`, `top_p`, `min_p`, `repeat_penalty`, `repeat_last_n`, `presence_penalty`, `frequency_penalty`, `num_ctx`) are hardcoded in `chat_app/llm.py`.
- The seed is fixed (`42`), so the same prompt gives the same reply, which is handy for testing.
- Errors: 400 invalid prompt, 502 Ollama error (e.g. model not pulled), 503 Ollama not reachable, 504 Ollama timed out.

### Chat configuration

Each business has at most one chat configuration. Both endpoints need a login and work on **your own** business, so there's no ID in the URL. Users without a business (e.g. `superuser`) get 403. `PUT` only changes `config_json`; `id`, `business` and `last_updated` are read-only. An invalid `config_json` returns 400 with every problem listed under `config_json` (see the rules under [Data model](#data-model)). The sample data gives `kopi_owner`'s business a configuration; the other businesses start with none.

### Access rules

- **Not logged in:** `401 Unauthorized`.
- **Business scope:** you only see and change records of **your own business** (the `business` on your user).
  - Lists only include your business's records.
  - Opening, editing or deleting another business's record returns **`403 Forbidden`**.
  - `business` is optional when creating; it defaults to your business. Sending another business's ID, whether on create or when trying to move a record, returns **`403 Forbidden`**.
  - Users without a business, like `superuser`, can view lists (which are empty) but get `403` for everything else.
- **Listing by business ID** (`/api/businesses/{business_id}/…`) is read-only. The checks run in this order:
  1. Not logged in: `401`.
  2. No business with that ID: `400`, with `{"business_id": ["Business configuration with ID 999 does not exist."]}`.
  3. Not your business (or your account has none): `403`.
  4. Otherwise: `200` with the paginated list.

  A non-numeric ID such as `/api/businesses/abc/products/` doesn't match the URL, so it returns `404`.
- **`quantity_sold` is read-only.** It's returned in responses, but sending it in a create or update returns `400 Bad Request`.
- **Validation errors return `400`** with a message per field, for example:
  - a negative quantity or price
  - a quantity over 1,000,000
  - a price with more than 2 decimal places
  - a name over 150 characters or an FAQ answer over 10,000 characters
  - a blank name
  - a product name or FAQ question that's already used in the same business

  The full list of rules is in [Data model](#data-model).

### Trying the APIs in Swagger UI

1. Start the server and open <http://127.0.0.1:8000/api/docs/>.
2. Click **Authorize** (top right) and log in one of two ways:
   - **basicAuth** (quickest): enter a username and password, e.g. `kopi_owner` / `123`.
   - **jwtAuth** (what `frontend-app` uses):
     1. Run `POST /api/auth/token/` with `{"username": "kopi_owner", "password": "123"}`.
     2. Copy the `access` value from the response.
     3. Paste it into **jwtAuth**, without the `Bearer ` prefix; Swagger adds it.
   Then click **Authorize** → **Close**.
3. Expand an endpoint, click **Try it out**, fill in the request and click **Execute**. For example, `GET /api/auth/me/` shows who you're logged in as and your business ID.

To switch user, click **Authorize** → **Logout** and log in as someone else (e.g. `bloom_owner`). Then try opening a Kopi & Co. product, such as `GET /api/products/1/`, to see the `403`.

You can also use your Django Admin login instead (**cookieAuth**). If you're logged in at `/admin/` in the same browser, Swagger requests use that session automatically. Business users can't log in to Admin, though, so basicAuth is the easiest way to test as them.

> [!NOTE]
> Username/password (Basic) authentication is only enabled while `DJANGO_DEBUG` is on, because it sends the password with every request. Use JWT everywhere else.

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
| `python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions` | Loads the sample data |
| `python manage.py flush --noinput` | Deletes all rows from every table (keeps the tables); see [Resetting the local database](#resetting-the-local-database) |
| `python manage.py test` | Runs all tests (see [Running tests](#running-tests)) |
| `python manage.py check` | Checks the project configuration for problems |
| `python manage.py spectacular --validate --file schema.yml` | Exports and validates the OpenAPI schema |

## Running tests

With the virtual environment active, from `configuration-service/`:

```bash
python manage.py test                      # run all tests
python manage.py test product_app          # one app
python manage.py test product_app.test_api # just the product/FAQ API tests
python manage.py test -v 2                 # verbose: list each test
```

Tests use a temporary database, so your `db.sqlite3` isn't touched.

| File | Covers |
| --- | --- |
| `auth_app/test_api.py` | JWT login, refresh + rotation, verify, logout (blacklist), `/api/auth/me/`, CORS for the `Authorization` header |
| `product_app/test_api.py` | Product and FAQ APIs: login required, business scoping and 403s, CRUD, read-only `quantity_sold`, validation; list-by-business endpoints (200 / 400 unknown ID / 401 / 403 other business, pagination, read-only) |
| `product_app/tests.py` | Product and FAQ model validation and database constraints |
| `auth_app/tests.py` | `BusinessUser` model, Django Admin pages load |
| `configuration_app/tests.py` | `BusinessConfiguration` model, random-number endpoint, CORS |
| `chat_app/tests.py` | `validate_chat_config` and `validate_chat_messages` rules; `ChatConfiguration` and `ChatSession` models (validation, uniqueness, `chat_state_id` must match a block); sample fixtures are valid |
| `chat_app/test_api.py` | Chat endpoint returns the reply, with the LLM mocked (no Ollama needed); chat configuration GET/PUT (401/403/404, create vs update, read-only fields, invalid `config_json` → 400) |

### Resetting the local database

To put the data back to the sample state, delete every row (the tables and migrations stay) and reload the fixtures:

```bash
python manage.py flush --noinput
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com
```

> [!WARNING]
> `flush` deletes **all** rows in every table: your own records, the superuser, sessions and blacklisted tokens. Drop `--noinput` to get a confirmation prompt first. Existing JWT tokens stop working, because their users no longer exist until the fixtures are reloaded (and anyone logged in has to log in again).

To delete the database file itself and rebuild it from the migrations (e.g. after migration problems):

```bash
rm db.sqlite3
python manage.py migrate
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions
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
│   ├── urls.py             # /admin, /api/configuration, /api/products, /api/faqs, /api/chat, /api/schema, /api/docs, /api/redoc
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
│   ├── serializers.py      # MeSerializer
│   ├── views.py            # Login/refresh/verify/logout (SimpleJWT) + MeView
│   ├── urls.py             # /api/auth/…
│   ├── test_api.py         # Auth API tests
│   ├── business_scope.py   # Business-ownership permission + serializer/viewset mixins
│   ├── models.py
│   └── tests.py            # Model + admin smoke tests
├── product_app/            # Products and FAQs
│   ├── fixtures/           # sample_products.json, sample_faqs.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py
│   ├── serializers.py      # ProductSerializer, FAQSerializer
│   ├── views.py            # ProductViewSet, FAQViewSet, BusinessProductListView, BusinessFAQListView
│   ├── urls.py             # /api/products/, /api/faqs/, /api/businesses/{id}/products|faqs/
│   ├── tests.py            # Model validation tests
│   └── test_api.py         # API tests
├── chat_app/               # ChatConfiguration (chat flow) + temporary one-off chat with the local LLM (Ollama)
│   ├── fixtures/           # sample_chat_configurations.json, sample_chat_sessions.json
│   ├── migrations/
│   ├── admin.py
│   ├── constants.py        # BLOCK_TYPES, MESSAGE_SENDERS
│   ├── models.py           # ChatConfiguration, ChatSession
│   ├── validators.py       # validate_chat_config, validate_chat_messages
│   ├── llm.py              # Ollama client, model, system prompt, hardcoded sampling options
│   ├── serializers.py      # Chat request/response, ChatConfigurationSerializer
│   ├── views.py            # ChatView, ChatConfigurationView
│   ├── urls.py             # /api/chat/, /api/chat/configuration/
│   ├── tests.py            # Validator + model tests
│   └── test_api.py         # Chat API (mocked LLM) + chat configuration API tests
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
