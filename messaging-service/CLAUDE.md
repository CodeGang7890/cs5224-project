# CLAUDE.md: messaging-service

Guidance for Claude Code when working in `messaging-service/`.

## What this is

A **Flask** backend for Ansera Business Admin, on port **8001**. It provides:
- `GET /`: hello world / health check.
- `POST /chat`: a **one-off** chat with a local LLM through **Ollama**. Single prompt in, single reply out, no history.

The sibling services are `../configuration-service` (Django, port 8000) and `../frontend-app` (Vite/React, port 5173). The user named the folder "messaing-service"; it was created as `messaging-service`, assumed to be a typo.

## Stack (keep to these; don't add dependencies without asking)

| Package | Why | Notes |
| --- | --- | --- |
| **Flask 3.1** | Web framework | App factory `create_app()` in `app/__init__.py`. |
| **flask-smorest 0.47** | Swagger UI + OpenAPI + request validation | `Api(app)`. Swagger UI at **`/docs`**, spec at `/openapi.json` (settings in `create_app`). Swagger UI assets load from the jsDelivr CDN. Routes use `flask_smorest.Blueprint` with `MethodView`s and `@bp.arguments` / `@bp.response` / `@bp.alt_response`. Errors use `flask_smorest.abort(code, message=...)`, which returns JSON `{code, status, message}`. |
| **marshmallow 4** (via flask-smorest) | Schemas | `app/schemas.py`. Invalid input returns **422**, with details under `errors.json`. marshmallow 4 **rejects unknown fields** by default. |
| **ollama 0.6** | LLM client | Used only in `app/llm.py`. `httpx` comes with ollama and is imported there to catch timeouts. |

- **No database.** The user asked for none so far.
- Add dependencies to `requirements.txt` with a version range. flask-smorest is pinned to a minor version (`<0.48`) because 0.x minors can break things.

## Configuration: `app/config.py` (ALL-CAPS constants, as requested)

- `PORT = 8001`.
- `OLLAMA_PORT = 11434` and `OLLAMA_HOST = f'http://localhost:{OLLAMA_PORT}'`.
- `OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'`.
- `SYSTEM_PROMPT`, `OLLAMA_TIMEOUT_SECONDS = 120`, `CHAT_PROMPT_MAX_LENGTH = 4000`, `API_TITLE` and `API_VERSION`.

Keep every tunable setting here as a constant. Don't hard-code values in routes. `run.py` also accepts `PORT`, `HOST` and `FLASK_DEBUG` from the environment for one-off overrides.

## Structure and conventions

- `app/llm.py`: `get_client()` is a lazy, shared `ollama.Client(host=OLLAMA_HOST, timeout=…)`. `generate_reply(prompt)` sends `[system: SYSTEM_PROMPT, user: prompt]` to `OLLAMA_MODEL` and returns `response.message.content`. It maps failures to its own exceptions, which `app/chat.py` turns into HTTP errors:
  - `ConnectionError` → `LLMUnavailableError` → **503**.
  - `httpx.TimeoutException` → `LLMTimeoutError` → **504**.
  - `ollama.ResponseError` (e.g. model not pulled) → `LLMError` → **502**.
- `app/chat.py`: blueprint `chat`, `POST /chat` → `{reply, model}`. **Stateless**: no history is kept between requests. Multi-turn chat would need a request schema with `messages` and, probably, storage; that's not built yet.
- `app/routes.py`: blueprint `main`, `GET /`.
- **Tests** (`python -m unittest -v`) never call a real model. They patch `app.llm.get_client` with a `MagicMock` whose `.chat` returns `SimpleNamespace(message=SimpleNamespace(content=...))`, or raises one of the errors above. Keep new LLM-dependent tests mocked.
- Every endpoint needs schemas and a docstring (the first line becomes the Swagger summary), so it shows up usefully in `/docs`.

## Not set up yet (add only when asked)

- **CORS.** `frontend-app` at `http://localhost:5173` will need it before calling this service from the browser, e.g. via flask-cors.
- **Auth.** Verifying configuration-service's SimpleJWT tokens (HS256, signed with Django's `SECRET_KEY`) would let only logged-in users chat.
- **Streaming responses** (`stream=True` in ollama), conversation history, and rate limiting.
- **A production WSGI server** (e.g. gunicorn).

## Commands (run from `messaging-service/`, with `.venv` active or via `.venv/bin/python`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:8001, Swagger UI at /docs
python -m unittest -v         # tests (Ollama mocked)
flask --app app routes        # list routes
```

Before finishing a change, run `python -m unittest -v`; it must pass.

## Environment notes for Claude

- **Ollama can't be reached from the sandbox.** All HTTP goes through the Apple Claude Code proxy. A request to `localhost:11434` (or any closed port) comes back as a proxy **502**, not a `ConnectionError`, so a live `/chat` call returns 502 with an "ACC Proxy" message. That's the sandbox, not the app. **Don't bypass the proxy** (e.g. `curl --noproxy`), which is blocked by policy. The user tests with the real LLM themselves; rely on the mocked unit tests.
- `python run.py` can bind a port here, but it can't be reached with curl through the proxy. Use the Flask test client instead.
- The user's shell sets `PYTHONPATH` to a Spark install, so `pip freeze` shows `pyspark`. Don't add it to `requirements.txt`.
