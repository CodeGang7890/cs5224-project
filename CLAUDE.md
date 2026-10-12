# CLAUDE.md: the whole repository

Guidance for Claude Code that applies to every service. Each service also has its own `CLAUDE.md`.

## Services

| Service | What | Port |
| --- | --- | --- |
| `configuration-service` | Django REST API: businesses, products, services, chats, orders, bookings. **Owns the database schema.** | 8000 |
| `payment-ingester` | Not built yet (port reserved); for now a script publishing dummy payment events | 8001 |
| `messaging-ingester` | FastAPI: WhatsApp webhooks → Pub/Sub (no database) | 8002 |
| `processing-service` | FastAPI + Gunicorn: pulls payment events, updates orders / bookings | 8003 |
| `messaging-service` | FastAPI + Gunicorn: the chat flow (LLM), one-off `/chat`, pulls WhatsApp messages | 8004 |
| `notification-job` | Python script, run hourly by cron: reads the database | none |
| `frontend-app` | Vite / React | 5173 |

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

  CI's `schema` job migrates a PostgreSQL database with Django and checks the messaging-service and processing-service models against it (`tests/test_schema.py`).
- Django's model defaults (`default=…`, `auto_now`, `new_payment_reference()`) and signals (for example, painting a booking into its provider's weekly availability) don't run outside Django. Code in another service that inserts or updates rows must set those values, and repeat those side effects, itself.

## The chat flow is in two places for now

The chat flow (everything behind the LLM chat endpoints) was copied from `configuration-service/chat_app` to `messaging-service/app/chat_flow`, with the ORM replaced by SQLAlchemy. The frontend's Chat Sandbox now sends its messages to messaging-service. configuration-service still has the same endpoints (the user asked not to remove them yet). Until they're removed there:

- **change both copies together**, and port their tests (`messaging-service/tests/test_chat_*.py`);
- everything else about chats stays in configuration-service only: listing chats, creating and deleting sandbox sessions, the chat settings, and answering questions.

## Logins

configuration-service issues the JWTs (SimpleJWT, HS256). messaging-service checks the access tokens itself (`app/auth.py`). Both must use the same `JWT_SIGNING_KEY`; docker-compose sets it.
