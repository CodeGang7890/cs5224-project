# processing-service

A **FastAPI** service, served by **Gunicorn**, on port **8003**. It will process payment events (see `TODO.txt`). For now it has a single hello world endpoint.

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
python run.py                                      # http://127.0.0.1:8003
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
│   ├── schemas.py
│   └── errors.py     # JSON error bodies (as in messaging-ingester)
├── tests/test_routes.py
├── gunicorn.conf.py
├── run.py            # development server
└── Dockerfile
```
