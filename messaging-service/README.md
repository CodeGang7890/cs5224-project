# Messaging Service

FastAPI backend for Ansera Business Admin. It runs on **port 8001**, because 8000 is used by `configuration-service` (Django).

It currently offers a one-off **chat** endpoint backed by a local LLM through [Ollama](https://ollama.com). It has no database.

## Tech stack

| Concern | Library |
| --- | --- |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) 0.142 |
| API docs + validation | FastAPI's built-in OpenAPI 3 + Swagger UI, [pydantic](https://docs.pydantic.dev/) v2 models |
| Server | [uvicorn](https://www.uvicorn.org/) (ASGI) |
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
python run.py                      # http://127.0.0.1:8001
```

Then open **Swagger UI at <http://127.0.0.1:8001/docs>** to try the API in the browser.

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
| `PORT` | `8001` | Port this service listens on |
| `OLLAMA_PORT` | `11434` | Port of the Ollama server |
| `OLLAMA_HOST` | `http://localhost:{OLLAMA_PORT}` | Ollama base URL |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct-q4_K_M` | Model used for chat |
| `SYSTEM_PROMPT` | "You are a helpful assistant for Ansera Business Admin. Answer clearly and concisely." | System message sent before every prompt |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | How long to wait for Ollama before giving up (`504`) |
| `CHAT_PROMPT_MAX_LENGTH` | `4000` | Maximum prompt length in characters |

`run.py` also reads a few environment variables for convenience. These override the defaults for a single run without editing code:

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `PORT` constant (`8001`) | e.g. `PORT=8002 python run.py` |
| `HOST` | `127.0.0.1` | Use `0.0.0.0` to accept connections from other machines or containers |
| `RELOAD` | `1` | `1` restarts the server automatically when the code changes; `0` turns that off |

You can also run uvicorn directly. `--factory` tells it to call the `create_app()` factory:

```bash
uvicorn app:create_app --factory --port 8001 --reload
```

## API

| Method | URL | What it does |
| --- | --- | --- |
| `GET` | `/` | Health check: `{"message": "Hello, World!"}` |
| `POST` | `/chat` | One-off chat: send one prompt, get one reply |
| `GET` | `/docs` | Swagger UI (interactive API docs) |
| `GET` | `/openapi.json` | OpenAPI 3 spec, which also lists every route |

### `POST /chat`

It takes a single prompt and returns a single reply. **No conversation history is kept**, so each request is independent. The model sees `SYSTEM_PROMPT` followed by your prompt.

```bash
curl -X POST http://127.0.0.1:8001/chat \
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

1. Open <http://127.0.0.1:8001/docs>.
2. Expand **POST /chat** and click **Try it out**.
3. Edit the example body, e.g. `{"prompt": "Hello!"}`, and click **Execute**.

## Running tests

```bash
python -m unittest -v
```

The tests mock the Ollama client, so they **don't need Ollama running**. They cover:
- a successful reply, and exactly what's sent to Ollama (model, system prompt, prompt);
- validation errors (422);
- 502, 503 and 504 when Ollama fails;
- the Swagger UI page and the OpenAPI spec.

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
│   └── chat.py         # Router "chat": POST /chat
├── tests/
│   ├── test_routes.py
│   └── test_chat.py    # /chat (Ollama mocked) + API docs
├── run.py              # Dev server entry point: uvicorn on config.PORT
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
> - Deployment: run uvicorn without `--reload`, e.g. `uvicorn app:create_app --factory --host 0.0.0.0 --port 8001 --workers 2`.
