# CLAUDE.md: the whole repository

Guidance for Claude Code that applies to every service. Each service also has its own `CLAUDE.md`.

## Services

| Service | What | Port |
| --- | --- | --- |
| `configuration-service` | Django REST API: businesses, products, services, chats, orders, bookings. **Owns the database schema.** | 8000 |
| `payment-ingester` | FastAPI + Gunicorn: creates Xendit Payment Sessions for the chat flow and receives Xendit webhooks → Pub/Sub | 8001 |
| `messaging-ingester` | FastAPI: WhatsApp webhooks → Pub/Sub (no database) | 8002 |
| `processing-service` | FastAPI + Gunicorn: pulls payment events, updates orders / bookings | 8003 |
| `messaging-service` | FastAPI + Gunicorn: the chat flow (LLM): the Chat Sandbox's API, and answering the WhatsApp messages it pulls from Pub/Sub; one-off `/chat` | 8004 |
| `notification-job` | Python script, run hourly by cron: payment and appointment reminders (logged for now; reads the database) | none |
| `frontend-app` | Vite / React | 5173 |
| `mock_whatsapp` | Local stand-in for WhatsApp / Meta (FastAPI + Jinja2 + SQLite, not in Docker): sends Meta's webhooks, fakes the Graph API for replies | 9000 |

`docker-compose.yml` runs them all locally, with PostgreSQL (host port 5433) and a Pub/Sub emulator (8085).

## The database: migrations only in configuration-service (the user's rule)

There is one PostgreSQL database, and **configuration-service (Django) owns its schema**:

- **Every schema change is a Django model change plus a Django migration** (`python manage.py makemigrations` in `configuration-service/`). This includes new tables, columns, indexes, constraints, renames and data migrations. Nothing else ever runs DDL against PostgreSQL.
- **Every other service only connects to query the data**: SELECT, plus INSERT / UPDATE / DELETE of rows where its job needs it. That covers messaging-service's chat flow (chat messages, orders, bookings, questions) and processing-service's payment updates. They map the tables they use with SQLAlchemy (`app/models.py`), and they must never:
  - create, alter or drop tables;
  - add Alembic or any other migration tool;
  - call `Base.metadata.create_all()` against PostgreSQL. Only the tests may do that, on a throwaway SQLite database.
- **Changing a table that other services use:** change the Django model and migration first, then update every SQLAlchemy mapping of that table. Today those are:
  - `messaging-service/app/models.py`
  - `processing-service/app/models.py`
  - `notification-job/app/models.py`

  CI's `schema` job migrates a PostgreSQL database with Django and checks the messaging-service, processing-service and notification-job models against it (`tests/test_schema.py`).
- Django's model defaults (`default=…`, `auto_now`, `new_payment_reference()`) and signals (for example, painting a booking into its provider's weekly availability) don't run outside Django. Code in another service that inserts or updates rows must set those values, and repeat those side effects, itself.

## The chat flow is only in messaging-service

The chat flow (everything behind the LLM chat endpoints) lives in `messaging-service/app/chat_flow` (SQLAlchemy). It was moved there from `configuration-service/chat_app`, then removed from configuration-service, with its `ollama` dependency (the user asked). Everything else about chats stays in configuration-service: listing chats, creating and deleting sandbox sessions, the chat settings, and answering questions. The shared rules (the step names, the detail field rules, the reply style presets) are in both services: change them together.

## Connecting WhatsApp

Businesses connect WhatsApp only with **Embedded Signup** ("Connect with Facebook", the user asked; the manual form was removed from frontend-app). It goes through our Meta app (`META_APP_ID` / `META_APP_SECRET`): frontend-app runs Meta's popup, and configuration-service exchanges the code, registers the number and points the business's WhatsApp account's webhook at its usual `/webhook/<business_id>` (a webhook override). messaging-ingester's `/webhook` is our app's own Callback URL. It's always on: until the `META_*` / `VITE_META_*` settings are set, the button shows but does nothing. Meta only allows the popup on HTTPS domains set on the app, so it can't be completed on localhost.

`WhatsAppConfiguration.connection_method` is `embedded_signup` for these and `manual` for older connections made with a business's own Meta app (e.g. the sample fixtures, which `mock_whatsapp` uses locally; there's no API to create new ones). Either way, messages, signature checks and replies work the same. Only manual connections store an App Secret (their own app's); Embedded Signup ones use `META_APP_SECRET` (`effective_app_secret`), so rotating it needs no data change.

Meta reports changes to a business's WhatsApp Business account (our app removed, the account deleted or offboarded, banned, reinstated) with `account_update` webhooks to our app's `/webhook`: messaging-ingester forwards them to configuration-service (`POST /api/internal/whatsapp/app/account-updates/`), which sets the connection's `status` (`disconnected` / `banned`), and frontend-app's WhatsApp card shows it with the reason. Nothing sets it back automatically (the user asked to keep it simple): reconnecting with Facebook does.

Embedded Signup tokens can expire (e.g. after 60 days, set by our Facebook Login for Business configuration): configuration-service saves `access_token_expires_time` (from Meta), the frontend warns the owner to reconnect from 7 days before (and once expired), and notification-job alerts the business's users 7 days and 1 day before and at expiry (logged for now). Reconnecting with Facebook renews the token. The 7 days are a constant in both configuration-service (`ACCESS_TOKEN_EXPIRY_WARNING`) and notification-job (`RECONNECT_ALERTS_BEFORE`), not a setting (the user asked): change them together. The API's `health` (`ok` / `expiring_soon` / `expired` / `disconnected` / `banned`) combines Meta's status and the expiry, so the frontend shows one answer.

## Logins

configuration-service issues the JWTs (SimpleJWT, HS256). messaging-service checks the access tokens itself (`app/auth.py`). Both must use the same `JWT_SIGNING_KEY`; docker-compose sets it.

Owners log in with a username and password, or with **Google / Facebook** through Google Cloud Identity Platform (Firebase Authentication): frontend-app runs the popup with the Firebase JS SDK and sends the ID token to configuration-service (`POST /api/auth/firebase/`, checked against `FIREBASE_PROJECT_ID`), which returns the same JWT pair, so nothing else changes. Owners can also **sign up** (`POST /api/auth/signup/`); a new account (or a first Google / Facebook login) has no business, so frontend-app asks for one first (`PUT /api/configuration/business/`). Empty `FIREBASE_PROJECT_ID` / `VITE_FIREBASE_*`: the Google / Facebook buttons do nothing; passwords and sign up still work. Logging in and signing up are rate limited per client IP (`DJANGO_LOGIN_RATE` / `DJANGO_SIGNUP_RATE`; behind Cloud Run, `DJANGO_NUM_PROXIES=1`).
