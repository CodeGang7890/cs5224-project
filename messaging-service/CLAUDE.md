# CLAUDE.md: messaging-service

Guidance for Claude Code when working in `messaging-service/`.

## What this is

A **FastAPI** backend for Ansera Business Admin, on port **8001**. It provides:
- `GET /`: hello world / health check.
- `POST /chat`: a **one-off** chat with a local LLM through **Ollama**. Single prompt in, single reply out, no history.

The sibling services are `../configuration-service` (Django, port 8000) and `../frontend-app` (Vite/React, port 5173). The user named the folder "messaing-service"; it was created as `messaging-service`, assumed to be a typo. It was first built with Flask + flask-smorest and later ported to FastAPI (the user asked), keeping the same endpoints, status codes and error bodies.

## Stack (keep to these; don't add dependencies without asking)

| Package | Why | Notes |
| --- | --- | --- |
| **FastAPI 0.142** | Web framework + OpenAPI + Swagger UI | App factory `create_app()` in `app/__init__.py`. Swagger UI at **`/docs`**, spec at `/openapi.json` (OpenAPI 3.1), ReDoc turned off (`redoc_url=None`). Swagger UI assets load from the jsDelivr CDN (FastAPI's default). Routes use `APIRouter`s (one module each, with a tag; tag descriptions are in `openapi_tags` in `create_app`). Errors are raised as `HTTPException(status_code, detail=...)`. |
| **pydantic 2** (via FastAPI) | Schemas | `app/schemas.py`. Invalid input returns **422**, with details under `errors.json`. `ChatRequest` uses `extra='forbid'` (unknown fields → 422) and `StrictStr` (no number → string coercion). |
| **uvicorn** | ASGI server | Started by `run.py`, with `factory=True` on `app:create_app`. |
| **ollama 0.6** | LLM client | Used only in `app/llm.py`. `httpx` comes with ollama and is imported there to catch timeouts. |
| **httpx2** | Tests only | Starlette 1.x's `TestClient` uses it; with plain `httpx` it emits a deprecation warning. Don't swap `llm.py`'s `httpx` import for it: ollama raises `httpx` exceptions. |

- **No database.** The user asked for none so far.
- Add dependencies to `requirements.txt` with a version range. FastAPI is pinned to a minor version (`<0.143`) because 0.x minors can break things.

## Configuration: `app/config.py` (ALL-CAPS constants, as requested)

- `PORT = 8001`.
- `OLLAMA_PORT = 11434` and `OLLAMA_HOST = f'http://localhost:{OLLAMA_PORT}'`.
- `OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'`.
- `SYSTEM_PROMPT`, `OLLAMA_TIMEOUT_SECONDS = 120`, `CHAT_PROMPT_MAX_LENGTH = 4000`, `API_TITLE` and `API_VERSION`.

Keep every tunable setting here as a constant. Don't hard-code values in routes. `run.py` also accepts `PORT`, `HOST` and `RELOAD` (default `1`, auto-reload) from the environment for one-off overrides.

## Structure and conventions

- `app/llm.py`: `get_client()` is a lazy, shared `ollama.Client(host=OLLAMA_HOST, timeout=…)`. `generate_reply(prompt)` sends `[system: SYSTEM_PROMPT, user: prompt]` to `OLLAMA_MODEL` and returns `response.message.content`. It maps failures to its own exceptions, which `app/chat.py` turns into HTTP errors:
  - `ConnectionError` → `LLMUnavailableError` → **503**.
  - `httpx.TimeoutException` → `LLMTimeoutError` → **504**.
  - `ollama.ResponseError` (e.g. model not pulled) → `LLMError` → **502**.
- `app/chat.py`: router tagged `chat`, `POST /chat` → `ChatResponse {reply, model}`. **Stateless**: no history is kept between requests. Multi-turn chat would need a request schema with `messages` and, probably, storage; that's not built yet. It's a plain `def`, so FastAPI runs the blocking Ollama call in a thread pool; keep blocking routes as `def`, not `async def`.
- `app/routes.py`: router tagged `main`, `GET /`.
- `app/errors.py`: exception handlers that keep the old flask-smorest error shapes. Every `HTTPException` (including 404/405) → `{code, status, message}`. `RequestValidationError` → `{code: 422, status, errors: {<location>: {<field>: [msg, ...]}}}`, where FastAPI's `body` location is renamed `json` (so `errors.json.prompt`), and a whole-body error (e.g. not a JSON object) goes under the field `_schema`. `status` is `http.HTTPStatus(code).phrase`; on Python 3.13+ that's "Unprocessable Content" for 422 (werkzeug said "Unprocessable Entity").
- **Tests** (`python -m unittest -v`) use `fastapi.testclient.TestClient(create_app())` and never call a real model. They patch `app.llm.get_client` with a `MagicMock` whose `.chat` returns `SimpleNamespace(message=SimpleNamespace(content=...))`, or raises one of the errors above. Keep new LLM-dependent tests mocked.
- Every endpoint needs typed request/response models, a `summary=` and (where useful) a docstring (it becomes the Swagger description), plus `responses=` entries for its error codes, so it shows up usefully in `/docs`. Document 422 with `ValidationErrorResponse` and other errors with `ErrorResponse`, since FastAPI's default 422 schema doesn't match the real body.

## Not set up yet (add only when asked)

- **CORS.** `frontend-app` at `http://localhost:5173` will need it before calling this service from the browser, e.g. via FastAPI's `CORSMiddleware` (no new dependency).
- **Auth.** Verifying configuration-service's SimpleJWT tokens (HS256, signed with Django's `SECRET_KEY`) would let only logged-in users chat.
- **Streaming responses** (`stream=True` in ollama), conversation history, and rate limiting.

## Commands (run from `messaging-service/`, with `.venv` active or via `.venv/bin/python`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:8001, Swagger UI at /docs
uvicorn app:create_app --factory --port 8001 --reload   # same, via uvicorn directly
python -m unittest -v         # tests (Ollama mocked)
```

Before finishing a change, run `python -m unittest -v`; it must pass.

## Environment notes for Claude

- **Ollama can't be reached from the sandbox.** All HTTP goes through the Apple Claude Code proxy. A request to `localhost:11434` (or any closed port) comes back as a proxy **502**, not a `ConnectionError`, so a live `/chat` call returns 502 with an "ACC Proxy" message. That's the sandbox, not the app. **Don't bypass the proxy** (e.g. `curl --noproxy`), which is blocked by policy. The user tests with the real LLM themselves; rely on the mocked unit tests.
- `python run.py` starts uvicorn, but binding the port fails here (`operation not permitted`). Use FastAPI's `TestClient` instead.
- The user's shell sets `PYTHONPATH` to a Spark install, so `pip freeze` shows `pyspark`. Don't add it to `requirements.txt`.
