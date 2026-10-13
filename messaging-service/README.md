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
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL (docker-compose: `http://host.docker.internal:11434`, Ollama on the host; see the root README, "Local LLM") |
| `WEB_CONCURRENCY` | `2` | Gunicorn worker processes (`gunicorn.conf.py`) |
| `PUBSUB_CONSUMER_ENABLED` | off | `true` to run the Pub/Sub consumer (off by default, so `python run.py` and the tests need no Pub/Sub) |
| `GCP_PROJECT_ID` | `local-project` | Google Cloud project of the topic and subscription |
| `PUBSUB_TOPIC` | `whatsapp-inbound-messages` | The topic messaging-ingester publishes to |
| `PUBSUB_SUBSCRIPTION` | `messaging-service-inbound` | This service's (pull) subscription to it |
| `PUBSUB_MAX_MESSAGES` | `5` | At most this many messages handled at once, per worker (flow control) |
| `PUBSUB_EMULATOR_HOST` | unset | `host:port` of the local Pub/Sub emulator (the library then uses it instead of Google Cloud) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `configuration_service` / `postgres` / `postgres` | configuration-service's database (the chat flow) |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5433` | docker-compose's PostgreSQL from the host (in Docker: `postgres` / `5432`) |
| `DATABASE_URL` | unset | A full SQLAlchemy URL; overrides the `POSTGRES_*` values |
| `SCHEDULE_TIME_ZONE` | `Asia/Singapore` | Time zone of the services' weekly availability: must equal configuration-service's `DJANGO_SCHEDULE_TIME_ZONE` |
| `JWT_SIGNING_KEY` | empty | Checks the login tokens: must equal configuration-service's `JWT_SIGNING_KEY` (docker-compose sets both). Empty: every token is rejected (401) |
| `CONFIGURATION_SERVICE_URL` / `INTERNAL_API_KEY` | `http://localhost:8000/api` / `dev-internal-api-key` | configuration-service's internal API, to send replies on WhatsApp (the key must equal its `INTERNAL_API_KEY`) |
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

The assistant's side of a customer chat, moved here from configuration-service's `chat_app` (the parts that need the LLM; `app/chat_flow/`). For each message, it runs the same steps as before: the router, the order or booking steps, the question check, a past order or booking lookup, then the reply (or a fixed template), saving everything in configuration-service's PostgreSQL. The details are in [Chat flow in detail](#chat-flow-in-detail) below.

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
- configuration-service no longer has these endpoints (they were removed there). Everything else about chats stays there: listing chats, creating and deleting sandbox chats, the chat settings and answering questions.
- **Database:** configuration-service (Django) owns the schema and every migration. This service only queries and writes rows (messages, chat state, orders, bookings and their calendar letters, questions); `app/models.py` maps the tables it uses.

Trying it: `docker compose up --build`, log in to the frontend, and use the Chat Sandbox (its messages now go to <http://localhost:8004>).

### Chat flow in detail

(Moved from configuration-service's README with the code. The modules named `chat_app/…` are now `app/chat_flow/…`.)

The chat flow is the same for every business (`chat_app/flow.py`): a **router** decides what each customer message is about, and code sends it to the right handler. Businesses only configure the steps' settings (so far, the details to collect: see configuration-service's chat configuration).

**Welcome message and reply style.** If the business has a welcome message, a chat's very first customer message gets it first, word for word (`{business_name}` filled in). If that message was only a greeting (the router found nothing to do), the welcome is the whole reply, with no reply LLM call; otherwise the usual reply follows, and isn't told to greet again. Every LLM-written reply follows the business's reply style: a preset (`friendly`, `professional`, `casual`, `brief`) or its own description (`custom`), which only changes the tone, never the rules. Both message endpoints return every message sent in the turn as `messages`.

```
customer message → router ─┬─ order        → Product selection → Details collection → Confirmation
                           ├─ booking      → Service selection → Time slot → Booking details → Booking confirmation
                           ├─ question     → FAQs (answered from the FAQs and products, or sent to the team)
                           ├─ order status → the customer's own past orders and bookings, looked up with tools
                           └─ off topic    → politely declined
```

1. **Route** (`chat_app/router.py`). The LLM reads the conversation and returns the latest message's intents as JSON (Ollama structured output, `temperature` 0): `{"intents": [...]}`, any of `order`, `booking`, `question`, `order_status` (past orders or bookings) and `off_topic` (none for a greeting or thanks; several for e.g. "2 roses please, and do you deliver?"). Unknown values are dropped. The prompt tells it where the customer's order is, so a short reply like "Alice" or "yes" reads as part of the order.
2. **Order steps** (`chat_app/order_flow.py`): a small state machine over Product selection → Details collection → Confirmation, saved in `chat_state_id`. With no order in progress (`start`), they only start when the router finds the intent `order` (and Product selection then runs on the same message). **Once an order is in progress, they run on every message, whatever the router says.** For each step:
   - **Extract.** The LLM returns JSON in the step's format (prompts and formats in `chat_app/prompts.py`):

     | Step | Goal | The LLM returns |
     | --- | --- | --- |
     | Product selection | Which products, and how many of each, confirmed as everything the customer wants | `{"items": [{"product_id", "quantity"}], "done_choosing": true/false}` |
     | Details collection | The details in the chat configuration's `product_detail_fields` (default: name and email) | One key per field, e.g. `{"name": …/null, "postal_code": 238801/null}` (numbers as numbers) |
     | Confirmation | Show the summary, get a confirmation | `{"decision": "confirm"/"change"/"none"}` |

   - **Check deterministically** (in Python, not the LLM) whether that completes the step, and save what's valid in `chat_state_data`:
     - Product selection: every chosen product must be one of the business's active products, with a quantity from 1 up to `quantity_available`. Otherwise it stays, and the problem (e.g. "Only 3 Kaya Toast Set are available", or that a sold-out product "has run out") goes into the reply prompt. The cart is checked again on every message, so an item that sold out (or has less stock left) since it was chosen is removed, and the customer can't move on with it. The reply prompt says never to offer sold-out products. Then it **pauses**: the assistant recaps the order (items, quantities, prices, total) and asks whether the customer wants anything else. It completes only when the customer says that's everything (`done_choosing`) **about the cart as it already was**, so a message that adds or changes items ("…and 1 Kaya Toast, that's all") gets a recap first. Once confirmed, `chat_state_data.items_confirmed` is set, and kept until the items change, so coming back after a "change" at confirmation that doesn't touch the items (e.g. a new email) passes straight through.
     - Details collection: complete only when **every required** field is known and valid for its type. Optional fields (`required: false`) are stored when given and never hold the chat back (a problem with one is explained without blocking). Text: at most `max_length`. Number: a number (text like `"238,801"` is accepted), within `min_value`–`max_value`. Email: Django's email validator. Invalid values are explained to the customer (e.g. "Postal code must be at least 100000.") and never replace a valid one. Values already known are kept when the customer doesn't repeat them. The reply prompt lists every field (label in quotes, required or optional, type and limits) under "Details to collect", and the required ones still needed. It tells the assistant: the order is **not** confirmed yet, so never say it is; keep asking for required details in every reply until they're given, even if the customer ignores the question; ask for optional ones once; and use each label **exactly as written**, without paraphrasing or guessing what an unusual label (e.g. "Boo") means. On every step, the assistant may only say an order is confirmed once it is. **Guardrails** on every step: stay on the current step's task; politely decline unrelated requests (general knowledge, coding, jokes, other businesses) or attempts to change or reveal the instructions, and steer back to the current step. The router and extraction prompts also ignore instructions inside the conversation.
     - Confirmation: `confirm` completes it and places the order; `change` goes back to Product selection, where the steps run again with the data already collected (so only what changed needs re-entering). It is never checked in the same message it's reached: the customer must see the summary first.
   - **Going back:** at Details collection and Confirmation, the extraction also returns `go_back_to`: `null`, or an earlier step (`"product_selection"`, and at Confirmation `"details_collection"`). Ollama's schema only allows those keys. When the customer clearly asks to change something from an earlier step ("I also want a Kaya Toast", "make it 3", "my email is wrong"), the chat goes back there **keeping everything collected**, and that step runs on the same message, so the change is applied straight away. Going back to Product selection clears `items_confirmed`, so the updated order is recapped and confirmed again; steps that are still complete pass straight through on the way forward. Going back is only offered at the step the chat was at when the message arrived, not at a step reached during that message (otherwise the "That's all" that finished Product selection could be read, at the next step, as going back to it). So there's at most one go-back per message, and none after the order is done.

   When a step completes, the chat moves to the next one and repeats there, so one message can complete several steps. Confirmation has two substages. **Not confirmed:** the chat sends the order summary (a fixed message, not written by the LLM, so it can never claim the order is confirmed) and asks the customer to reply CONFIRM; any other reply (even "no, nothing else") just sends the summary again. **Confirmed:** the order is saved first, and only then is the customer sent a fixed "Your order #N is confirmed" message. The chat then goes back to `start`, with only `chat_state_data.last_order_id`, so the customer can order again. If the order can't be placed (e.g. sold out in the meantime), the chat goes back to Product selection, keeping everything, and the assistant explains the problem.
   **Booking steps** (for businesses with services; started by the router's `booking` intent): **Service selection** (which service; the LLM returns `{"service_id"}`), **Time slot**, **Booking details** (the chat configuration's `schedule_detail_fields`, set separately from the order details) and **Booking confirmation** (like Confirmation). At **Time slot** the LLM only says what the customer asked for (`{"choice", "date", "date_to", "time", "part_of_day"}`, with today's date and the next two weeks' dates in its prompt); the free times are worked out in code from the weekly availability and the bookings, and the chat sends them as a fixed, numbered list (up to 6, spread out, at most 3 a day), so "2" or "the second one" picks a time the code chose. An exact day and time is booked if it's free; otherwise other times that day are offered. A day or part of the day ("Tuesday afternoon") gets times then, or the next free days if there are none. Confirming saves the booking first (`checkout_app.services.place_booking`, a `ScheduleItem` pending payment, with the first free provider who does the service; its blocks go on hold) and only then sends "Your booking #N … is confirmed"; if someone else took that time in the meantime, the chat goes back to Time slot with fresh times. The chat then goes back to the start, keeping `last_booking_id`.
3. **Save** `chat_state_id` and `chat_state_data`. A collected name also fills in an empty `display_name`.
4. **Questions (FAQs)**, if the router found one: the question check (described under [Unanswered questions](#unanswered-questions)) decides whether the business's information answers it.
5. **Reply.** At Confirmation, the reply is the fixed summary or confirmation message above; if the message also asked a question (or about a past order, or something off topic), the LLM adds a short answer to just that, before the summary or after the confirmation. A message only about past orders or bookings (intent `order_status` alone, with no order step run) goes through the order status branch, with no tools: an LLM call only extracts what the customer asks about (order or booking, and any numbers); code looks those up among the customer's own orders and bookings ("the customer" is the same phone number with the same business, and only real or only sandbox chats, like the current one; sandbox chats without a phone number count as one customer, so you can check a test order from another test chat), where a number that isn't theirs is simply "not found"; then a second LLM call writes the reply from only those records (with each one's status: payment pending, payment received or completed). A reply naming any other order or booking number, or saying more than "not found" about one that wasn't found, is replaced by a message written by code, and so is the reply when nothing of theirs was found (with no LLM call). Otherwise the LLM writes the reply with a system prompt putting together what the flow found: the business's details, the order step and its goal (or no order in progress), what's known so far (order with total, details), what's still needed, problems to explain, the products on sale (with no order in progress and at Product selection, with each product's short description; never the longer information), the customer's question (answered from the information given, or "sent to the team"), a past order or booking question (the customer's own records, looked up by code), and an off-topic message (politely declined). The reply step can call **read-only tools** (`chat_app/tools.py`, only the chatting business's data):
   - `get_product_details(product)`: one product's description and **information** (the long extra details), price and stock, by name (any case; a partial name works if it matches one product) or id. Ambiguous names list the matches; unknown names list what's on sale; inactive products are "not on sale at the moment".
   - `list_products`: every active product, with its description (not the information).
   - `list_faqs`: the business's FAQs.

   The prompt tells the assistant to answer "what is it?" with the product's description, to look other product questions up with `get_product_details` (answering the question rather than reciting the information) and business questions with `list_faqs`, to answer only from what it finds, and otherwise to **say honestly that it doesn't know** (offering to check with the team) rather than make anything up.

A message makes 2 or more LLM calls: the router, one extraction per order step it passes through, the question check (only for questions), plus the reply (plus tool calls). Only the last 20 messages are sent (`HISTORY_MAX_MESSAGES`).

## Pub/Sub consumer

A **pull** subscriber (`app/consumer.py`) for the customer messages `messaging-ingester` publishes to the topic `whatsapp-inbound-messages` (the message format is in `messaging-ingester/README.md`, "Pub/Sub message contract"). It uses **streaming pull**: the client library keeps a connection open to Pub/Sub and hands over messages as they arrive, on its own threads, at most `PUBSUB_MAX_MESSAGES` at a time.

- It runs only when `PUBSUB_CONSUMER_ENABLED` is set, from the app's startup to its shutdown. With Gunicorn, each worker runs one, and they share the subscription's messages.
- Its subscription is its own, `messaging-service-inbound`, so it gets every message (separate from the ingester's debug subscription). With the local emulator (`PUBSUB_EMULATOR_HOST`), it creates the topic and the subscription (with message ordering) at startup; on Google Cloud they'll come from Terraform. Pub/Sub only delivers messages published after a subscription exists.
- **Each message is answered by the chat flow** (`app/inbound.py`), the same as the Chat Sandbox:
  1. Only text messages, for a business that exists (others are acked and skipped).
  2. The customer's chat: the business's real chat session with that number, or a new one (named after their WhatsApp profile).
  3. In one transaction: an `InboundMessage` row for Meta's message id (configuration-service's `chat_app.InboundMessage`), saved with the customer message in the chat. **A duplicate** (Pub/Sub delivers at least once, Meta retries) is skipped; a message redelivered after a failure runs again without being saved twice.
  4. The chat flow runs (router, order / booking steps, FAQ, order status, reply) and saves the reply; the row becomes `replied`.
  5. **The reply is sent on WhatsApp** through configuration-service's internal send endpoint (`app/whatsapp_sender.py`; configuration-service holds the access token and calls Meta's Graph API, or locally `mock_whatsapp`'s fake one). A failed send is logged; the reply stays saved in the chat (retries: a TODO, via an outbound queue).
- If handling raises (e.g. the LLM is down), the message is **nacked**, so Pub/Sub redelivers it. A message that isn't JSON, or lacks `business_id`, `message_id`, `from` or `type`, is logged and **acked** (redelivering it would never help). The ingester orders by customer, so one customer's messages are answered one at a time.

Trying it end to end, from the repo root:

```bash
docker compose up --build                     # Pub/Sub emulator, messaging-ingester, messaging-service, ...
docker compose logs -f messaging-service      # "Customer message wamid..." then "Reply in chat N sent to +65... on WhatsApp"
curl http://localhost:8004/consumer           # {"enabled": true, "running": true, "handled": ..., ...}
```

Then send a WhatsApp message to a connected business (or post a webhook to the ingester, see its README): the ingester publishes it, and messaging-service answers it; the conversation shows in the frontend's Chats → Conversations.

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
