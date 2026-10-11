# processing-service

A **FastAPI** service, served by **Gunicorn**, on port **8003**. It pulls the **payment events** payment-ingester publishes to Pub/Sub (topic `payment-events`). For each, it updates the order or booking with that payment reference in configuration-service's PostgreSQL (SQLAlchemy). The flow is a draft: the invoice and telling the customer are TODOs.

| Port | Service |
| --- | --- |
| 8000 | configuration-service |
| 8001 | payment-ingester (reserved, coming soon) |
| 8002 | messaging-ingester |
| **8003** | **processing-service** |
| 8004 | messaging-service |

## API

| Method | Path | |
| --- | --- | --- |
| `GET` | `/` | Hello world / health check: `{"message": "Hello, world! processing-service is running"}` |

Swagger UI is at <http://localhost:8003/docs>, and the OpenAPI spec at `/openapi.json`.

## Pub/Sub consumer

`app/consumer.py` is a **pull** subscriber (streaming pull) on its own subscription, `processing-service-payments`, to the topic `payment-events`. Each message's data is JSON `{payment_reference, status}` (32 hex characters; `success` / `fail`; see `payment-ingester/README.md`).

- **Valid:** it goes through the payment flow (below), then is acked. A repeated event changes nothing.
- **Unknown payment reference, or not pending payment** (e.g. already completed): logged as an error and acked.
- **Processing raised:** nacked, so Pub/Sub redelivers it.
- **Malformed:** logged as a warning and acked, so it isn't redelivered forever.

It starts and stops with the app. Each Gunicorn worker runs one, and they share the messages. It's off unless `PUBSUB_CONSUMER_ENABLED` is set; docker-compose turns it on. With the emulator (`PUBSUB_EMULATOR_HOST`), the consumer creates its subscription itself.

To try it end to end, publish dummy events with payment-ingester's script, then watch `docker compose logs -f processing-service`.

## Payment flow (`app/payments.py`)

In one transaction, with the row locked:

1. Find the product order (`checkout_app_orderitem`) or booking (`checkout_app_scheduleitem`) with the payment reference. None: `PaymentNotFoundError`.
2. Only `pending_payment` changes: `success` → `payment_received`, `fail` → `payment_failed`. Already in that status: nothing changes. Any other status: `PaymentStatusConflictError`.
3. **Product orders:** nothing else is stored. configuration-service works out each product's on hold / sold / available quantities from the orders' statuses: payment received still holds them, and a failed payment holds nothing, so they're available again.
4. **Bookings:** the provider's weekly availability letters are stored, and Django's signals don't run here, so `app/schedule.py` (a port of configuration-service's `checkout_app.schedule`) paints them. Paid: on hold (H) → booked (X) over the duration, and the buffer where open. Failed: back to available (O).
5. TODOs: generate the invoice and upload it to object storage; tell the customer (WhatsApp API or Gmail API).

`app/models.py` maps only the columns the flow needs. configuration-service (Django) owns the schema and every migration: this service never creates or alters tables.

| Variable | Default | |
| --- | --- | --- |
| `PUBSUB_CONSUMER_ENABLED` | off | `true` / `1` / `yes` turns the consumer on |
| `GCP_PROJECT_ID` | `local-project` | |
| `PUBSUB_TOPIC` / `PUBSUB_SUBSCRIPTION` | `payment-events` / `processing-service-payments` | |
| `PUBSUB_MAX_MESSAGES` | `5` | Messages handled at once, per worker |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `configuration_service` / `postgres` / `postgres` | configuration-service's database |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5433` | docker-compose: `postgres` / `5432` |
| `DATABASE_URL` | unset | A full SQLAlchemy URL; overrides the above |
| `SCHEDULE_TIME_ZONE` | `Asia/Singapore` | Must equal configuration-service's `DJANGO_SCHEDULE_TIME_ZONE` |
| `PUBSUB_EMULATOR_HOST` | unset | `host:port` of the local emulator (docker-compose: `pubsub-emulator:8085`) |

## Running

### With Docker and Gunicorn (recommended)

From the repository root:

```bash
docker compose up --build processing-service   # http://localhost:8003
```

The image runs `gunicorn -c gunicorn.conf.py "app:create_app()"`: `WEB_CONCURRENCY` Uvicorn workers (default 2) on `0.0.0.0:$PORT` (default 8003; Cloud Run sets `PORT`).

### Without Docker (development, auto-reload)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                                      # http://127.0.0.1:8003 (consumer off)
gunicorn -c gunicorn.conf.py "app:create_app()"   # or as in Docker
```

## Tests

```bash
python -m unittest -v
```

## Project structure

```
processing-service/
├── app/
│   ├── __init__.py   # create_app()
│   ├── config.py     # PORT = 8003, WORKERS, API title
│   ├── routes.py     # GET /
│   ├── consumer.py   # Pub/Sub pull consumer of the payment events
│   ├── payments.py   # the payment flow
│   ├── schedule.py   # painting a booking into its provider's weeks
│   ├── models.py     # SQLAlchemy models of configuration-service's tables
│   ├── db.py         # engine and sessions (lazy)
│   ├── schemas.py
│   └── errors.py     # JSON error bodies (as in messaging-ingester)
├── tests/          # test_routes.py, test_consumer.py (fake Pub/Sub clients), test_payments.py (SQLite)
├── gunicorn.conf.py
├── run.py            # development server
└── Dockerfile
```
