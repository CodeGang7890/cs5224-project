# processing-service

A **FastAPI** service, served by **Gunicorn**, on port **8003**. It pulls the **payment events** payment-ingester publishes to Pub/Sub (topic `payment-events`). For now it logs each one's payment ID and status, then waits 2 seconds; the real logic (see `TODO.txt`) comes later.

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

`app/consumer.py` is a **pull** subscriber (streaming pull) on its own subscription, `processing-service-payments`, to the topic `payment-events`. Each message's data is JSON `{payment_id, status}` (`success` / `fail`; see `payment-ingester/README.md`).

- **Valid:** it's logged (`Payment pay_…: success`), then waits `PROCESSING_SECONDS` and is acked.
- **Processing raised:** nacked, so Pub/Sub redelivers it.
- **Malformed:** logged as a warning and acked, so it isn't redelivered forever.

It starts and stops with the app. Each Gunicorn worker runs one, and they share the messages. It's off unless `PUBSUB_CONSUMER_ENABLED` is set; docker-compose turns it on. With the emulator (`PUBSUB_EMULATOR_HOST`), the consumer creates its subscription itself.

To try it end to end, publish dummy events with payment-ingester's script, then watch `docker compose logs -f processing-service`.

| Variable | Default | |
| --- | --- | --- |
| `PUBSUB_CONSUMER_ENABLED` | off | `true` / `1` / `yes` turns the consumer on |
| `GCP_PROJECT_ID` | `local-project` | |
| `PUBSUB_TOPIC` / `PUBSUB_SUBSCRIPTION` | `payment-events` / `processing-service-payments` | |
| `PUBSUB_MAX_MESSAGES` | `5` | Messages handled at once, per worker |
| `PROCESSING_SECONDS` | `2` | Stand-in for the real work |
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
│   ├── schemas.py
│   └── errors.py     # JSON error bodies (as in messaging-ingester)
├── tests/          # test_routes.py, test_consumer.py (fake Pub/Sub clients)
├── gunicorn.conf.py
├── run.py            # development server
└── Dockerfile
```
