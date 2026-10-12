# CLAUDE.md: messaging-service

Guidance for Claude Code when working in `messaging-service/`.

## What this is

A **FastAPI** backend for Ansera Business Admin, on port **8004** (it moved from 8001, which is reserved for payment-ingester). It provides:
- `GET /`: hello world / health check.
- `POST /chat`: a **one-off** chat with a local LLM through **Ollama**. Single prompt in, single reply out, no history.
- A **Pub/Sub pull consumer** (the user asked) of the customer messages `../messaging-ingester` publishes, and `GET /consumer` (its status). For now it logs each message and `time.sleep(PROCESSING_SECONDS)`s before acking; it isn't connected to the chat flow yet.
- **The chat flow** (the user asked: moved from configuration-service's `chat_app`, the parts that need the LLM): `POST /api/chat/sandbox-sessions/{pk}/messages/` (the frontend's Chat Sandbox, login required) and `POST /api/chat/sessions/messages/` (a customer message, public). **Same paths, status codes and JSON bodies as Django** (DRF-style errors), so callers only change the host. configuration-service still has them too (the user asked not to remove them yet): **keep `app/chat_flow` and `chat_app` in step until they're removed there** (see the repo-root `CLAUDE.md`). Listing chats, sandbox sessions (create / delete), the chat settings and answering questions stay in configuration-service.

The sibling services are `../configuration-service` (Django, port 8000) and `../frontend-app` (Vite/React, port 5173). The user named the folder "messaing-service"; it was created as `messaging-service`, assumed to be a typo. It was first built with Flask + flask-smorest and later ported to FastAPI (the user asked), keeping the same endpoints, status codes and error bodies.

## Stack (keep to these; don't add dependencies without asking)

| Package | Why | Notes |
| --- | --- | --- |
| **FastAPI 0.142** | Web framework + OpenAPI + Swagger UI | App factory `create_app()` in `app/__init__.py`. Swagger UI at **`/docs`**, spec at `/openapi.json` (OpenAPI 3.1), ReDoc turned off (`redoc_url=None`). Swagger UI assets load from the jsDelivr CDN (FastAPI's default). Routes use `APIRouter`s (one module each, with a tag; tag descriptions are in `openapi_tags` in `create_app`). Errors are raised as `HTTPException(status_code, detail=...)`. |
| **pydantic 2** (via FastAPI) | Schemas | `app/schemas.py`. Invalid input returns **422**, with details under `errors.json`. `ChatRequest` uses `extra='forbid'` (unknown fields → 422) and `StrictStr` (no number → string coercion). |
| **Gunicorn 26 + uvicorn-worker** | Production / Docker server (the user asked, like the other FastAPI services) | `gunicorn.conf.py` (bind `0.0.0.0:$PORT`, `WEB_CONCURRENCY` workers, `uvicorn_worker.UvicornWorker`; Uvicorn's own `uvicorn.workers` is deprecated; `timeout` 150 > `OLLAMA_TIMEOUT_SECONDS`, `graceful_timeout` 30); the Dockerfile runs `gunicorn -c gunicorn.conf.py "app:create_app()"`. |
| **uvicorn** | ASGI server | `run.py` (dev, reload), with `factory=True` on `app:create_app`; also the Gunicorn workers. |
| **google-cloud-pubsub 2.x** | The pull consumer | `app/consumer.py`: streaming pull (`SubscriberClient.subscribe(path, callback, flow_control=FlowControl(max_messages=PUBSUB_MAX_MESSAGES))`). Clients are created in `Consumer.start()`, so building the app needs no credentials. |
| **ollama 0.6** | LLM client | Used only in `app/llm.py`. `httpx` comes with ollama and is imported there to catch timeouts. |
| **SQLAlchemy 2.0 + psycopg 3** | configuration-service's PostgreSQL, for the chat flow | `app/models.py` (models of the Django tables: only the columns used; `AwareDateTime` = Django's aware datetimes; `Json` = jsonb), `app/db.py` (lazy engine; `get_sessionmaker()` with `expire_on_commit=False`). |
| **PyJWT 2** | Logins | `app/auth.py`: configuration-service's SimpleJWT access tokens (HS256, `JWT_SIGNING_KEY`). |
| **httpx2** | Tests only | Starlette 1.x's `TestClient` uses it; with plain `httpx` it emits a deprecation warning. Don't swap `llm.py`'s `httpx` import for it: ollama raises `httpx` exceptions. |

- **The database belongs to configuration-service (the user's rule): no migrations here, ever.** This service only queries rows and writes them where the chat flow needs it (chat messages, chat state, orders, bookings and their calendar letters, unanswered questions). Never create, alter or drop tables, add Alembic, or `create_all()` against PostgreSQL (tests do it on SQLite only). A schema change is a Django migration in configuration-service first, then the mapping in `app/models.py`; `tests/test_schema.py` (CI's `schema` job, on a Django-migrated PostgreSQL) checks they match. Django's defaults and signals don't run here: inserts set every column (e.g. `payment_reference`, times), and placing a booking paints its provider's week (`schedule.sync_booking`).
- Add dependencies to `requirements.txt` with a version range. FastAPI is pinned to a minor version (`<0.143`) because 0.x minors can break things.

## Configuration: `app/config.py` (ALL-CAPS constants, as requested)

- `PORT = 8004`, `WORKERS` (env `WEB_CONCURRENCY`, 2).
- `OLLAMA_PORT = 11434` and `OLLAMA_HOST` (env, default `f'http://localhost:{OLLAMA_PORT}'`; docker-compose: `http://ollama:11434`, the `ollama` container (CPU only); `OLLAMA_HOST=http://host.docker.internal:11434` for the Mac's own, which must listen on 0.0.0.0).
- Pub/Sub (all env, see the README): `PUBSUB_CONSUMER_ENABLED` (off by default), `GCP_PROJECT_ID`, `PUBSUB_TOPIC` (`whatsapp-inbound-messages`), `PUBSUB_SUBSCRIPTION` (`messaging-service-inbound`), `PUBSUB_MAX_MESSAGES` (5), `PROCESSING_SECONDS` (2); the library reads `PUBSUB_EMULATOR_HOST`.
- `OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'`.
- `SYSTEM_PROMPT`, `OLLAMA_TIMEOUT_SECONDS = 120`, `CHAT_PROMPT_MAX_LENGTH = 4000`, `API_TITLE` and `API_VERSION`.
- The chat flow's `OLLAMA_OPTIONS` / `STRUCTURED_OPTIONS` / `MAX_TOOL_ROUNDS` (copied from `chat_app/llm.py`; `/chat` sends no options, as before).
- Database (env, like configuration-service's): `POSTGRES_DB` / `USER` / `PASSWORD` / `HOST` / `PORT` (default `localhost:5433`: compose's PostgreSQL from the host), `DATABASE_URL` overrides; `SCHEDULE_TIME_ZONE` (must equal Django's `DJANGO_SCHEDULE_TIME_ZONE`).
- `JWT_SIGNING_KEY` (must equal configuration-service's; empty → every token 401), `JWT_ALGORITHM = 'HS256'`; `CORS_ALLOWED_ORIGINS` (default `http://localhost:5173`).

Keep every tunable setting here as a constant. Don't hard-code values in routes. `run.py` also accepts `PORT`, `HOST` and `RELOAD` (default `1`, auto-reload) from the environment for one-off overrides.

## Structure and conventions

- `app/llm.py`: `get_client()` is a lazy, shared `ollama.Client(host=OLLAMA_HOST, timeout=…)`. `generate_reply(prompt)` sends `[system: SYSTEM_PROMPT, user: prompt]` to `OLLAMA_MODEL` and returns `response.message.content`. It maps failures to its own exceptions, which `app/chat.py` turns into HTTP errors:
  - `ConnectionError` → `LLMUnavailableError` → **503**.
  - `httpx.TimeoutException` → `LLMTimeoutError` → **504**.
  - `ollama.ResponseError` (e.g. model not pulled) → `LLMError` → **502**.
- `app/chat.py`: router tagged `chat`, `POST /chat` → `ChatResponse {reply, model}`. **Stateless**: no history is kept between requests. Multi-turn chat would need a request schema with `messages` and, probably, storage; that's not built yet. It's a plain `def`, so FastAPI runs the blocking Ollama call in a thread pool; keep blocking routes as `def`, not `async def`.
- `app/routes.py`: router tagged `main`, `GET /`.
- `app/consumer.py`: `parse(data)` (JSON object with `business_id`, `message_id`, `from`, `type`, else `InvalidMessageError`), `process(payload)` (log + sleep: replace with the real work), `handle(message, stats)` (malformed → ack + `skipped`; `process` raised → nack + `failed`; else ack + `handled`), `ensure_emulator_resources()` (emulator only: topic + ordered subscription, `AlreadyExists` ok, retries), `Consumer` (`start(emulator)` / `stop()`, `running`, `stats`). Dedup on `message_id` is a TODO for when there's real work.
- `create_app(consumer=None)`: builds a `Consumer()` when `PUBSUB_CONSUMER_ENABLED`; the lifespan (`lifespan_for`) starts it (in the thread pool; with the emulator when `PUBSUB_EMULATOR_HOST` is set) and stops it on shutdown. Each Gunicorn worker runs one; they share the subscription. Tests pass a `Consumer` with fake clients. `app/consumer_routes.py`: `GET /consumer` → `ConsumerStatus`.
- `app/errors.py`: exception handlers that keep the old flask-smorest error shapes. Every `HTTPException` (including 404/405) → `{code, status, message}`. `RequestValidationError` → `{code: 422, status, errors: {<location>: {<field>: [msg, ...]}}}`, where FastAPI's `body` location is renamed `json` (so `errors.json.prompt`), and a whole-body error (e.g. not a JSON object) goes under the field `_schema`. `status` is `http.HTTPStatus(code).phrase`; on Python 3.13+ that's "Unprocessable Content" for 422 (werkzeug said "Unprocessable Entity").
- **The chat flow, `app/chat_flow/`**: each module is a copy of its `chat_app` namesake (`constants`, `validators`, `prompts`, `router`, `order_flow`, `flow`, `tools`, `past_orders`, `questions`: only `ask_business`) plus ports of what they used from Django: `checkout.py` (`checkout_app/services.py` `place_order` / `place_booking` + `checkout_app/validators.py` + `ScheduleItem.clean`), `schedule.py` (`checkout_app/schedule.py`: free times, `start_problem`, `sync_booking`), `stock.py` (derived quantities), `settings.py` (`ChatSettings.for_business` = `ChatConfiguration.for_business`), `emails.py` (Django's `EmailValidator`, checked identical), `dates.py`, `errors.py` (`ValidationError`). Changes from Django are only mechanical: functions that query take a session `db`; the flow takes a `sessionmaker` and **reads in short sessions** (closed before LLM calls, like Django's autocommit) and **writes in transactions** (`sessions.begin()`; `append_chat_message`, `commit_turn` with `begin_nested()` savepoints around `place_order` / `place_booking`, `ask_business`); `SELECT … FOR UPDATE` as in Django; JSON columns are reassigned, never mutated. The LLM calls are in `app/llm.py` (`generate_structured`, `generate_chat_reply`).
- `app/chat_api.py`: the two endpoints. Checks in Django's order: login (`app/auth.py`: SimpleJWT's 401 bodies: not provided / `token_not_valid` / `user_not_found` / `user_inactive`, `WWW-Authenticate: Bearer realm="api"`), then no business 403 / unknown 404 / other business 403 / not sandbox 400, then the body (`app/drf.py`: DRF `CharField` / `IntegerField` rules and messages, e.g. `{"message": ["This field may not be blank."]}`); LLM errors → 502 / 503 / 504 `{"detail": …}`. The turn runs in the thread pool. `get_sessions()` is a dependency (tests override it).
- **Tests** (`python -m unittest -v`) use `fastapi.testclient.TestClient(create_app())` and never call a real model or Pub/Sub (`tests/test_consumer.py`: `FakeMessage`, `MagicMock` subscriber / publisher; `time.sleep` patched). They patch `app.llm.get_client` with a `MagicMock` whose `.chat` returns `SimpleNamespace(message=SimpleNamespace(content=...))`, or raises one of the errors above. Keep new LLM-dependent tests mocked. The chat flow tests (`tests/test_chat_*.py`) are ports of `chat_app`'s and `checkout_app`'s tests: `tests/chat_helpers.py` (`DatabaseTestCase`: a fresh SQLite file per test with `create_all` and SAVEPOINTs enabled, `self.make` factories, `self.get` / `self.all`; `ApiTestCase`: `self.client`, `self.login(user)` with a token signed by `TEST_SIGNING_KEY`; `FlowTestMixin` + the fake LLM, as in Django) and `tests/schedule_helpers.py` (`open_week`, `book`, `day_letters`…). When a `chat_app` test changes, change its port too.
- Every endpoint needs typed request/response models, a `summary=` and (where useful) a docstring (it becomes the Swagger description), plus `responses=` entries for its error codes, so it shows up usefully in `/docs`. Document 422 with `ValidationErrorResponse` and other errors with `ErrorResponse`, since FastAPI's default 422 schema doesn't match the real body.

## Not set up yet (add only when asked)

- **Connecting the Pub/Sub consumer to the chat flow** (WhatsApp messages answered by it), and sending replies.
- **Streaming responses** (`stream=True` in ollama), conversation history, and rate limiting.

## Commands (run from `messaging-service/`, with `.venv` active or via `.venv/bin/python`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:8004, Swagger UI at /docs (consumer off)
gunicorn -c gunicorn.conf.py "app:create_app()"          # as in Docker
gunicorn --check-config -c gunicorn.conf.py "app:create_app()"   # check Gunicorn's settings without starting it
uvicorn app:create_app --factory --port 8004 --reload   # same, via uvicorn directly
python -m unittest -v         # tests (Ollama mocked)
```

Before finishing a change, run `python -m unittest -v`; it must pass.

## Environment notes for Claude

- **Ollama can't be reached from the sandbox.** All HTTP goes through the Apple Claude Code proxy. A request to `localhost:11434` (or any closed port) comes back as a proxy **502**, not a `ConnectionError`, so a live `/chat` call returns 502 with an "ACC Proxy" message. That's the sandbox, not the app. **Don't bypass the proxy** (e.g. `curl --noproxy`), which is blocked by policy. The user tests with the real LLM themselves; rely on the mocked unit tests.
- `python run.py` starts uvicorn, but binding the port fails here (`operation not permitted`). Use FastAPI's `TestClient` instead.
- compose's PostgreSQL (`localhost:5433`) is sometimes unreachable from the sandbox; the tests don't need it (SQLite).
- The user's shell sets `PYTHONPATH` to a Spark install, so `pip freeze` shows `pyspark`. Don't add it to `requirements.txt`.
