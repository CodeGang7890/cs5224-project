# Messaging Service

FastAPI backend for Ansera Business Admin. It runs on **port 8004** (8000 is `configuration-service`, 8001 is reserved for `payment-ingester`, 8002 is `messaging-ingester` and 8003 is `processing-service`).

It offers:

- **The chat flow**, moved from configuration-service: the Chat Sandbox's messages and customer messages get the assistant's reply (a local LLM through [Ollama](https://ollama.com)), with orders, bookings and questions saved to configuration-service's PostgreSQL. See [Chat flow](#chat-flow).
- A one-off **chat** endpoint (`POST /chat`).
- A **Pub/Sub consumer**: a pull subscriber for the customer WhatsApp messages `messaging-ingester` publishes. For now it logs each one, waits, and acknowledges it; see [Pub/Sub consumer](#pubsub-consumer).

In Docker it's served by **Gunicorn** with Uvicorn workers.

## Tech stack

| Concern | Library |
| --- | --- |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) 0.142 |
| API docs + validation | FastAPI's built-in OpenAPI 3 + Swagger UI, [pydantic](https://docs.pydantic.dev/) v2 models |
| Server | [Gunicorn](https://gunicorn.org/) with Uvicorn workers ([uvicorn-worker](https://github.com/Kludex/uvicorn-worker)) in Docker; [uvicorn](https://www.uvicorn.org/) with reload for `python run.py` |
| Database | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 + psycopg 3: configuration-service's PostgreSQL (its schema; no migrations here) |
| Logins | [PyJWT](https://pyjwt.readthedocs.io/): configuration-service's access tokens |
| Pub/Sub | [google-cloud-pubsub](https://cloud.google.com/python/docs/reference/pubsub/latest) (streaming pull subscriber) |
| LLM | [ollama](https://github.com/ollama/ollama-python) Python client → a local Ollama server |
| Tests | Python's built-in `unittest` + FastAPI's `TestClient` (Ollama is mocked) |

## Prerequisites

- **Python 3.10+** (developed with 3.14). Check with `python3 --version`.
- **Ollama** running on port **11434** (the default), with the model pulled:

  ```bash
  ollama pull qwen2.5:7b-instruct-q4_K_M
  ollama list                       # should list the model
  ```

## Getting started

Run all commands from the `messaging-service/` folder.

```bash
cd messaging-service

# 1. Create and activate a virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the development server
python run.py                      # http://127.0.0.1:8004
```

Then open **Swagger UI at <http://127.0.0.1:8004/docs>** to try the API in the browser.

When you come back later, reactivate the virtual environment and start the server:

```bash
source .venv/bin/activate
python run.py
```

> [!NOTE]
> Moving from the old Flask version? Re-run `pip install -r requirements.txt`. You can remove the old packages with `pip uninstall flask flask-smorest marshmallow`.

## Configuration

All settings are constants in **`app/config.py`**. Edit them there:

| Constant | Default | What it is |
| --- | --- | --- |
| `PORT` | `8004` | Port this service listens on |
| `OLLAMA_PORT` | `11434` | Port of the Ollama server |
| `OLLAMA_HOST` | `http://localhost:{OLLAMA_PORT}` | Ollama base URL |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct-q4_K_M` | Model used for chat |
| `SYSTEM_PROMPT` | "You are a helpful assistant for Ansera Business Admin. Answer clearly and concisely." | System message sent before every prompt |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | How long to wait for Ollama before giving up (`504`) |
| `CHAT_PROMPT_MAX_LENGTH` | `4000` | Maximum prompt length in characters |

These also come from environment variables (docker-compose sets them):

| Variable | Default | What it is |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL (docker-compose: `http://ollama:11434`, its Ollama container) |
| `WEB_CONCURRENCY` | `2` | Gunicorn worker processes (`gunicorn.conf.py`) |
| `PUBSUB_CONSUMER_ENABLED` | off | `true` to run the Pub/Sub consumer (off by default, so `python run.py` and the tests need no Pub/Sub) |
| `GCP_PROJECT_ID` | `local-project` | Google Cloud project of the topic and subscription |
| `PUBSUB_TOPIC` | `whatsapp-inbound-messages` | The topic messaging-ingester publishes to |
| `PUBSUB_SUBSCRIPTION` | `messaging-service-inbound` | This service's (pull) subscription to it |
| `PUBSUB_MAX_MESSAGES` | `5` | At most this many messages handled at once, per worker (flow control) |
| `PROCESSING_SECONDS` | `2` | How long each message waits before its ack (a stand-in for the real work) |
| `PUBSUB_EMULATOR_HOST` | unset | `host:port` of the local Pub/Sub emulator (the library then uses it instead of Google Cloud) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `configuration_service` / `postgres` / `postgres` | configuration-service's database (the chat flow) |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5433` | docker-compose's PostgreSQL from the host (in Docker: `postgres` / `5432`) |
| `DATABASE_URL` | unset | A full SQLAlchemy URL; overrides the `POSTGRES_*` values |
| `SCHEDULE_TIME_ZONE` | `Asia/Singapore` | Time zone of the services' weekly availability: must equal configuration-service's `DJANGO_SCHEDULE_TIME_ZONE` |
| `JWT_SIGNING_KEY` | empty | Checks the login tokens: must equal configuration-service's `JWT_SIGNING_KEY` (docker-compose sets both). Empty: every token is rejected (401) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated browser origins allowed to call the API (the frontend) |

`run.py` also reads a few environment variables for convenience. These override the defaults for a single run without editing code:

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `PORT` constant (`8004`) | e.g. `PORT=8002 python run.py` |
| `HOST` | `127.0.0.1` | Use `0.0.0.0` to accept connections from other machines or containers |
| `RELOAD` | `1` | `1` restarts the server automatically when the code changes; `0` turns that off |

You can also run uvicorn directly. `--factory` tells it to call the `create_app()` factory:

```bash
uvicorn app:create_app --factory --port 8004 --reload
```

### With Docker and Gunicorn

From the repo root, `docker compose up --build messaging-service` starts it (with the Pub/Sub emulator) on <http://localhost:8004>. In Docker, **Gunicorn** serves the app, as it would in production:

```bash
gunicorn -c gunicorn.conf.py "app:create_app()"   # the Dockerfile's CMD
```

`gunicorn.conf.py`: bind `0.0.0.0:$PORT` (8004; Cloud Run sets `PORT`), `WEB_CONCURRENCY` workers (2) of `uvicorn_worker.UvicornWorker`, a 150 s request timeout (longer than `OLLAMA_TIMEOUT_SECONDS`, for `/chat`), 30 s to finish the messages being handled when shutting down, and access logs to stdout.

## API

| Method | URL | What it does |
| --- | --- | --- |
| `GET` | `/` | Health check: `{"message": "Hello, World!"}` |
| `POST` | `/chat` | One-off chat: send one prompt, get one reply |
| `GET` | `/consumer` | The Pub/Sub consumer's status: on or off, running, and how many messages it handled, skipped and failed |
| `POST` | `/api/chat/sandbox-sessions/{id}/messages/` | The Chat Sandbox: send `{message}` in one of your business's sandbox chats, get the reply + `debug` (login required) |
| `POST` | `/api/chat/sessions/messages/` | A customer message: `{business_id, phone_number, message}` → the reply (public) |
| `GET` | `/docs` | Swagger UI (interactive API docs) |
| `GET` | `/openapi.json` | OpenAPI 3 spec, which also lists every route |

### `POST /chat`

It takes a single prompt and returns a single reply. **No conversation history is kept**, so each request is independent. The model sees `SYSTEM_PROMPT` followed by your prompt.

```bash
curl -X POST http://127.0.0.1:8004/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Suggest three names for a neighbourhood café."}'
```

```json
{ "reply": "1. The Corner Cup ...", "model": "qwen2.5:7b-instruct-q4_K_M" }
```

| Status | When |
| --- | --- |
| `200` | Success: `{reply, model}` |
| `422` | Invalid body: missing, blank, non-string or too-long `prompt`, unknown fields, or a body that isn't a JSON object. Details are under `errors.json`. |
| `502` | Ollama returned an error, e.g. the model isn't pulled (`ollama pull …`) |
| `503` | Ollama isn't reachable. Is it running on `OLLAMA_PORT`? |
| `504` | Ollama didn't answer within `OLLAMA_TIMEOUT_SECONDS` |

Error responses look like `{"code": 503, "status": "Service Unavailable", "message": "Could not connect to Ollama at http://localhost:11434."}`.

Validation errors (422) list the messages by location (`json` is the request body) and then by field:

```json
{ "code": 422, "status": "Unprocessable Content", "errors": { "json": { "prompt": ["Field required"] } } }
```

> [!TIP]
> The first request after Ollama starts can take a while, because it loads the model into memory. Later requests are faster.

### Trying it in Swagger UI

1. Open <http://127.0.0.1:8004/docs>.
2. Expand **POST /chat** and click **Try it out**.
3. Edit the example body, e.g. `{"prompt": "Hello!"}`, and click **Execute**.

## Chat flow

The assistant's side of a customer chat, moved here from configuration-service's `chat_app` (the parts that need the LLM; `app/chat_flow/`). For each message, it runs the same steps as before: the router, the order or booking steps, the question check, a past order or booking lookup, then the reply (or a fixed template), saving everything in configuration-service's PostgreSQL. The details are in configuration-service's README, "Chat flow".

| Endpoint | Who | Like configuration-service's |
| --- | --- | --- |
| `POST /api/chat/sandbox-sessions/{id}/messages/` | The frontend's Chat Sandbox. Log in with configuration-service and send its access token (`Authorization: Bearer …`) | `SandboxChatMessageView` |
| `POST /api/chat/sessions/messages/` | A customer (public, like a webhook) | `CustomerMessageView` |

- **The same as configuration-service's**: paths, request bodies, responses, status codes and error bodies (`{"detail": …}`, `{"message": ["This field may not be blank."]}`), so callers only change the host:
  - 401: not logged in;
  - 403: no business, or another business's chat;
  - 404: no such chat;
  - 400: a real chat (not a sandbox one), or an invalid body;
  - 502 / 503 / 504: Ollama failed.
- configuration-service still has these endpoints too, for now. Everything else about chats stays there: listing chats, creating and deleting sandbox chats, the chat settings and answering questions.
- **Database:** configuration-service (Django) owns the schema and every migration. This service only queries and writes rows (messages, chat state, orders, bookings and their calendar letters, questions); `app/models.py` maps the tables it uses.

Trying it: `docker compose up --build`, log in to the frontend, and use the Chat Sandbox (its messages now go to <http://localhost:8004>).

## Pub/Sub consumer

A **pull** subscriber (`app/consumer.py`) for the customer messages `messaging-ingester` publishes to the topic `whatsapp-inbound-messages` (the message format is in `messaging-ingester/README.md`, "Pub/Sub message contract"). It uses **streaming pull**: the client library keeps a connection open to Pub/Sub and hands over messages as they arrive, on its own threads, at most `PUBSUB_MAX_MESSAGES` at a time.

- It runs only when `PUBSUB_CONSUMER_ENABLED` is set, from the app's startup to its shutdown. With Gunicorn, each worker runs one, and they share the subscription's messages.
- Its subscription is its own, `messaging-service-inbound`, so it gets every message (separate from the ingester's debug subscription). With the local emulator (`PUBSUB_EMULATOR_HOST`), it creates the topic and the subscription (with message ordering) at startup; on Google Cloud they'll come from Terraform. Pub/Sub only delivers messages published after a subscription exists.
- **For now**, each message is logged (`Customer message <message_id> for business <id> from <number> (<type>): <text>`), then it waits `PROCESSING_SECONDS`, then it's acknowledged. The chat flow will go there later.
- If handling raises, the message is **nacked**, so Pub/Sub redelivers it. A message that isn't JSON, or lacks `business_id`, `message_id`, `from` or `type`, is logged and **acked** (redelivering it would never help).
- Pub/Sub delivers at least once, and the ingester may publish a message twice: when there's real work, drop duplicates by `message_id` first.

Trying it end to end, from the repo root:

```bash
docker compose up --build                     # Pub/Sub emulator, messaging-ingester, messaging-service, ...
docker compose logs -f messaging-service      # "Customer message wamid... for business ... from +65...: ..."
curl http://localhost:8004/consumer           # {"enabled": true, "running": true, "handled": ..., ...}
```

Then send a WhatsApp message to a connected business (or post a webhook to the ingester, see its README): the ingester publishes it, and messaging-service logs it.

## Running tests

```bash
python -m unittest -v
```

The tests mock the Ollama client, so they **don't need Ollama running**. They cover:
- a successful reply, and exactly what's sent to Ollama (model, system prompt, prompt);
- validation errors (422);
- 502, 503 and 504 when Ollama fails;
- the Swagger UI page and the OpenAPI spec;
- the chat flow (`tests/test_chat_*.py`, ported from configuration-service's `chat_app` / `checkout_app` tests): every step of ordering and booking, the router, tools, past orders, questions, the welcome message and reply style, the validators, and both endpoints (logins, permissions, validation, LLM errors). They use a throwaway SQLite database (`tests/chat_helpers.py`), so they **don't need PostgreSQL**; `tests/test_schema.py` checks the models against a Django-migrated PostgreSQL when `SCHEMA_DATABASE_URL` is set (CI does);
- the Pub/Sub consumer (`tests/test_consumer.py`, with fake Pub/Sub clients, so no emulator is needed): a message is logged, processed and acked; a failure nacks; a malformed one is acked and skipped; the emulator's topic and subscription are created (and retried while it starts); the streaming pull's subscription and flow control; it starts and stops with the app; `GET /consumer`.

## Project structure

```
messaging-service/
├── app/
│   ├── __init__.py     # create_app(): FastAPI app, error handlers, includes the routers
│   ├── config.py       # ALL settings: ports, Ollama host/model, system prompt, limits
│   ├── errors.py       # JSON error bodies: {code, status, message} and {code, status, errors} (422)
│   ├── llm.py          # Ollama client wrapper: generate_reply(), maps failures to LLMError types
│   ├── schemas.py      # pydantic request/response models (also drive the Swagger docs)
│   ├── routes.py       # Router "main": GET /
│   ├── chat.py         # Router "chat": POST /chat
│   ├── consumer.py     # Pub/Sub pull consumer: parse, process (log + sleep), ack / nack, emulator setup
│   ├── consumer_routes.py  # Router "consumer": GET /consumer
│   ├── chat_api.py     # Router "chat flow": the sandbox and customer message endpoints
│   ├── chat_flow/      # the chat flow (ported from configuration-service's chat_app + checkout_app)
│   ├── auth.py         # configuration-service's login tokens (SimpleJWT-compatible checks)
│   ├── drf.py          # DRF-style validation and error bodies, for the chat flow endpoints
│   ├── db.py           # SQLAlchemy engine and sessions (lazy)
│   └── models.py       # SQLAlchemy models of configuration-service's tables (no migrations here)
├── tests/
│   ├── test_routes.py
│   ├── test_chat.py    # /chat (Ollama mocked) + API docs
│   ├── test_chat_*.py  # the chat flow (SQLite; helpers in chat_helpers.py, schedule_helpers.py)
│   ├── test_schema.py  # the models against Django's schema (SCHEMA_DATABASE_URL)
│   └── test_consumer.py  # the Pub/Sub consumer (fake clients)
├── run.py              # Dev server entry point: uvicorn on config.PORT, with reload
├── gunicorn.conf.py    # Gunicorn settings (Docker / production)
├── Dockerfile          # python:3.14-slim, runs Gunicorn
└── requirements.txt
```

## Adding an endpoint

1. Define request/response models in `app/schemas.py`.
2. Add a route to an `APIRouter`, either an existing one or a new module included in `create_app()`:

   ```python
   @router.get('/ping', summary='Ping')
   def ping() -> Message:
       return Message(message='pong')
   ```

FastAPI validates the request against the parameter types and the response against the return type, and generates the Swagger docs from both. Use a plain `def` for routes that make blocking calls (like Ollama's client): FastAPI runs them in a thread pool.

> [!NOTE]
> - Swagger UI loads its scripts from the jsDelivr CDN, so the browser needs internet access for `/docs`.
> - Deployment: run Gunicorn, as the Dockerfile does: `gunicorn -c gunicorn.conf.py "app:create_app()"`.
