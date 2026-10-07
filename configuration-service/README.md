# Configuration Service

Django REST API backend for Ansera Business Admin. It has five Django apps: `configuration_app`, `auth_app`, `product_app`, `chat_app` and `checkout_app`. So far they contain the data models, Django Admin screens, sample fixtures, CRUD APIs for products and FAQs, a chat endpoint backed by a local LLM (Ollama), and one sample endpoint. It uses a local SQLite database for now.

## Tech stack

| Concern | Library |
| --- | --- |
| Web framework | [Django](https://www.djangoproject.com/) 6.1 |
| REST APIs | [Django REST Framework (DRF)](https://www.django-rest-framework.org/) |
| Swagger / OpenAPI docs | [drf-spectacular](https://drf-spectacular.readthedocs.io/) (OpenAPI 3, Swagger UI + ReDoc) |
| CORS | [django-cors-headers](https://github.com/adamchainz/django-cors-headers) |
| API filtering / sorting | [django-filter](https://django-filter.readthedocs.io/) |
| Authentication | [djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/) (JWT access/refresh tokens) |
| LLM (chat) | [ollama](https://github.com/ollama/ollama-python) Python client, talking to a local [Ollama](https://ollama.com/) server |
| Database | SQLite (local file `db.sqlite3`); a real database will be integrated later |

## Prerequisites

- **Python 3.12+** (required by Django 6.1). Check with `python3 --version`.

## Getting started

Run all commands from the `configuration-service/` folder.

```bash
cd configuration-service

# 1. Create and activate a virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply database migrations (creates db.sqlite3 on first run)
python manage.py migrate

# 4. Load sample data (businesses, business users, products, FAQs)
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions sample_order_items

# 5. Create the local admin superuser (username: superuser, password: 123)
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com

# 6. Start the development server
python manage.py runserver         # http://127.0.0.1:8000
```

Then log in to Django Admin at <http://127.0.0.1:8000/admin/> with **`superuser` / `123`**. The superuser can view, add, edit and delete everything.

> [!WARNING]
> `superuser` / `123` is a throwaway login for local development only. Never create it on a shared or deployed database. `--noinput` skips Django's password-strength checks, which is why the command accepts such a short password. On Windows (PowerShell), run `$env:DJANGO_SUPERUSER_PASSWORD="123"` first, then run the `createsuperuser` command without the `DJANGO_SUPERUSER_PASSWORD=123` prefix.

To use a different port: `python manage.py runserver 8080`.

When you come back later, you only need to reactivate the virtual environment and start the server:

```bash
source .venv/bin/activate
python manage.py migrate           # safe to re-run; applies any new migrations
python manage.py runserver
```

## Sample data (fixtures)

The fixtures are JSON files in each app's `fixtures/` folder. Load them all with:

```bash
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions sample_order_items
```

| Fixture | File | Contents |
| --- | --- | --- |
| `sample_business_configurations` | `configuration_app/fixtures/` | 3 businesses: Kopi & Co. Café, Bloom & Twine Florist Studio (with a full, realistic description), FitLab Personal Training |
| `sample_business_users` | `auth_app/fixtures/` | 4 business users linked to those businesses |
| `sample_products` | `product_app/fixtures/` | 19 products (one of them inactive). Each has a short description and longer information. Bloom & Twine Florist Studio has 12 realistic products across fresh, dried / preserved, soap and crochet flowers ($5.90 to $288, two of them sold out), each with detailed information (materials, size, how long it lasts, care, options, delivery). Kopi & Co. Café's 5 have long, detailed information (ingredients, sizes, options, allergens, storage, and a few product FAQs) for testing `get_product_details`, with some details deliberately left out to test "I don't know" |
| `sample_faqs` | `product_app/fixtures/` | 32 FAQs: 12 for Kopi & Co. Café (hours, reservations, halal, delivery, payment, vegetarian options, sugar levels, catering, parking, Wi-Fi, pets, cancellations), 18 for Bloom & Twine Florist Studio (delivery, pickup, hours, payment, care, card messages, cancellations, substitutions, corporate, weddings, workshops, allergies and pets…), 2 for FitLab |
| `sample_chat_configurations` | `chat_app/fixtures/` | 2 chat flows, both start → product selection → details collection → confirmation: Kopi & Co. Café (asks for name, email and pickup time) and Bloom & Twine Florist Studio (asks for name, card message and delivery date) |
| `sample_chat_sessions` | `chat_app/fixtures/` | 14 customer chats: 11 with Kopi & Co. Café (at different steps of its flow, over 1–12 Sep, one with no messages yet), 2 with Bloom & Twine Florist Studio (one choosing products, one giving details), 1 with FitLab. `+6591234567` chats with both the café and the florist. Plus 2 sandbox (test) chats for Kopi & Co. Café, one without a phone number |
| `sample_order_items` | `checkout_app/fixtures/` | 5 orders: 4 for Kopi & Co. Café (one per status, plus a pending sandbox order) and 1 for Bloom & Twine Florist Studio. They aren't linked to chats, and their stock wasn't reserved |

Every sample account uses the password **`123`**, so you can log in as anyone while testing:

| Username | Business | Can log in to |
| --- | --- | --- |
| `kopi_owner` | Kopi & Co. Café (1) | API only |
| `bloom_owner` | Bloom & Twine Florist Studio (2) | API only |
| `bloom_staff` | Bloom & Twine Florist Studio (2) | API only |
| `fitlab_owner` | FitLab Personal Training (3) | API only |
| `superuser` (created by the `createsuperuser` command, not a fixture) | none | Django Admin (full access). Gets 403 on product/FAQ changes, because it has no business. |

Business users aren't staff, so they can't log in to Django Admin.

Notes:
- Fixtures use fixed IDs, so re-running `loaddata` resets those records to the sample values rather than creating duplicates. Records you created yourself are kept.
- Load them in one command, as shown above. The records depend on each other: users, products, FAQs, chat configurations and chat sessions point to businesses, and chat sessions' `chat_state_id` points to a block in the business's chat configuration.
- `loaddata` saves records as-is, without running model validation. When you edit a fixture, keep the data within the model rules.

## Data model

| App | Model | Fields |
| --- | --- | --- |
| `configuration_app` | `BusinessConfiguration` | `id`, `business_name` (≤150 chars), `description` (≤2,000 chars, optional), `location` (≤255 chars) |
| `auth_app` | `BusinessUser` | Every field of Django's built-in user (username, password, email, first/last name, `is_staff`, `is_superuser`, `is_active`, groups, permissions, `last_login`, `date_joined`), plus `business` → `BusinessConfiguration` (optional) |
| `product_app` | `Product` | `id`, `business` → `BusinessConfiguration`, `name` (≤150 chars), `description` (≤300 chars, optional: the short summary the chat assistant gives customers), `information` (≤5,000 chars, optional: extra details the assistant looks up to answer specific questions; customers don't see it as is), `price` (≥0, 2 decimal places, up to 99,999,999.99), `quantity_available` / `quantity_on_hold` / `quantity_sold` (whole numbers ≥0, default 0), `is_active` (default true) |
| `product_app` | `FAQ` | `id`, `business` → `BusinessConfiguration`, `question` (≤300 chars), `answer` (≤10,000 chars) |
| `chat_app` | `ChatSession` | `id`, `business` → `BusinessConfiguration`, `phone_number` (the customer's, international format e.g. `+6591234567`), `display_name` (≤150 chars, optional), `created_time` (defaults to now), `last_chat_time`, `chat_message_json` (the conversation, see below), `chat_state_id` (the flow block the customer is at, or empty), `chat_state_data` (what the chat flow has collected so far, see below), `is_sandbox` (a test chat from the Chat Sandbox; default false) |
| `chat_app` | `ChatConfiguration` | `id`, `business` → `BusinessConfiguration` (one per business), `config_json` (the chat flow, see below), `last_updated` (set automatically on every save) |
| `checkout_app` | `OrderItem` | `id`, `business` → `BusinessConfiguration`, `chat_session` → `ChatSession` (the chat it was placed in; cleared if the chat is deleted), `is_sandbox`, `order_data` (what was ordered and the customer details, see below), `order_status` (`pending_payment` (default), `payment_received` or `order_completed`), `created_time`, `updated_time` |

Rules enforced by Django validation (e.g. in Django Admin) **and** by the database:
- Price and quantities can't be negative.
- Business names, locations, product names, FAQ questions and FAQ answers can't be empty.
- Product names and FAQ questions must be unique **within a business**. Different businesses can reuse them.

`ChatConfiguration.config_json` is a list of blocks, e.g. `{"id": 1, "next_block_id": 2, "block_type": "START_BLOCK", "position_x": 100, "position_y": 100}`. `chat_app/validators.py` (`validate_chat_config`) checks it on every validated save, e.g. in Django Admin:
- Every block has exactly those five fields, plus an optional `fields` on a `DETAILS_COLLECTION_BLOCK` (see below) and a required `message` on a `SEND_MESSAGE_BLOCK`: a non-blank string of at most 4,096 characters (the message it sends). `message` on any other block type is rejected.
- `id` is an integer or a non-blank string (e.g. a UUID), unique within the list.
- `next_block_id` is `null` or the `id` of another block in the list.
- `block_type` is one of `START_BLOCK`, `PRODUCT_SELECTION_BLOCK`, `DETAILS_COLLECTION_BLOCK`, `CONFIRMATION_BLOCK`, `SEND_MESSAGE_BLOCK` (defined in `chat_app/constants.py`). There must be exactly one `START_BLOCK`; other types can repeat.
- `position_x` / `position_y` are numbers.

A `DETAILS_COLLECTION_BLOCK`'s `fields` lists the customer details it asks for (set in the frontend's Workflow editor by clicking the block). Without it, the block asks for name and email (`DEFAULT_DETAIL_FIELDS` in `chat_app/constants.py`). Example:

```json
"fields": [
  {"key": "name", "label": "Receiver name", "type": "text", "max_length": 150},
  {"key": "email", "label": "Email", "type": "email"},
  {"key": "postal_code", "label": "Postal code", "type": "number", "min_value": 100000, "max_value": 999999},
  {"key": "notes", "label": "Customisation notes", "type": "text", "max_length": 200, "description": "e.g. less sugar"}
]
```

- 1 to 20 fields. Each has `key`, `label` and `type`, and only the optional keys its type allows.
- `key`: lowercase letters, digits and underscores, starting with a letter, at most 40 characters, unique in the block. The customer's answer is stored under it in `chat_state_data.details`.
- `label`: non-blank, at most 100 characters. It's what the assistant asks for.
- `type`: `text`, `number`, `email` or `phone`.
- `description` (any type, optional): a hint for the assistant, at most 300 characters.
- `required` (any type, optional): `false` for an optional detail; missing means required. At least one field must be required (otherwise the block would move on before asking anything).
- `max_length` (`text` only, optional): 1–2,000 (default 500).
- `min_value` / `max_value` (`number` only, optional): numbers, minimum ≤ maximum.
- `fields` on any other block type is rejected. Like the other rules, every problem is listed.

`ChatSession` rules (checked by Django validation, e.g. in Django Admin):
- `phone_number` is required and unique **within a business** (both also enforced by the database). Different businesses can each have a chat with the same number.
- **Sandbox sessions** (`is_sandbox = true`) are exempt: the phone number is optional (still validated if given), may repeat, and a business can have any number of them.
- `chat_message_json` is a list of messages, oldest first: `{"message": "Hi", "sent_by": "customer", "message_time": "2026-09-01T09:00:00+08:00"}`. `validate_chat_messages` (`chat_app/validators.py`) checks that `message` is non-blank (≤4,096 chars), `sent_by` is `customer`, `business-manual` or `business-automated` (defined in `chat_app/constants.py`), and `message_time` is an ISO 8601 date-time with a timezone, in chronological order. An empty list is fine.
- `chat_state_id` is empty, or the `id` of a block in the business's chat configuration (the type must match too: `"2"` is not block `2`). If the business has no chat configuration, it must be empty.
- `chat_state_data` is an object; every key is optional (`{}` means nothing collected yet). `validate_chat_state_data` checks: `items`, a list of `{product_id, name, unit_price, quantity}` (the chosen products; `name` and `unit_price` are a snapshot, `unit_price` a decimal string like `"5.50"`, `quantity` ≥1); `items_confirmed`, true once the customer said those items are everything; `details`, the customer details collected so far by field key (non-blank strings or numbers, e.g. `{"name": "Alice", "postal_code": 238801}`); `completed`, true once the customer confirmed the order. Example: `{"items": [{"product_id": 1, "name": "Kopi C", "unit_price": "1.80", "quantity": 2}], "details": {"name": "Alice"}}`.

`OrderItem.order_data` is `{"items": [...], "details": {...}}`, checked by `validate_order_data` (`checkout_app/validators.py`):
- `items`: at least one `{product_id, name, unit_price, quantity}`, one per product. `name` and `unit_price` are what the customer was shown (`unit_price` a decimal string like `"5.50"`: ≥0, at most 2 decimal places); `quantity` is 1–1,000,000.
- `details`: the customer details collected in the chat, by field key (non-blank strings or numbers). Can be empty if the flow has no Details collection block.
- `order_status` must be one of the three statuses (also enforced by the database).

When a business is deleted:
- Its **products, FAQs, chat configuration, chat sessions and orders are deleted** with it.
- Its **users are kept**, with their business link cleared.

`BusinessUser` is the project's user model (`AUTH_USER_MODEL = 'auth_app.BusinessUser'`). In code, refer to it with `django.contrib.auth.get_user_model()` or `settings.AUTH_USER_MODEL`.

## APIs

### Authentication (JWT)

| Method | URL | Body → response | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/auth/token/` | `{username, password}` → `{access, refresh}` | Log in |
| `POST` | `/api/auth/token/refresh/` | `{refresh}` → `{access, refresh}` | Get a new access token. The refresh token also rotates: use the new one, because the old one is now invalid. |
| `POST` | `/api/auth/token/verify/` | `{token}` → `{}` | Check that a token is valid (200) or not (401) |
| `POST` | `/api/auth/logout/` | `{refresh}` → `{}` | Log out: revokes (blacklists) the refresh token |
| `GET` | `/api/auth/me/` | → profile | Your profile: `id`, `username`, `email`, `first_name`, `last_name`, **`business`** (your `BusinessConfiguration` ID, or `null`), `business_name`, `is_staff`, `is_superuser`. Requires login. |

- **Access token:** send it as `Authorization: Bearer <access>`. It's valid for **15 minutes**.
- **Refresh token:** valid for **7 days**. It can be used only once, because each refresh returns a new one.
- **Settings:** lifetimes and rotation are configured in `SIMPLE_JWT` in `config/settings.py`.
- **Endpoint access:** the login, refresh, verify and logout endpoints are public; `me/` needs a login.

### Products and FAQs

All of these require you to be logged in.

| Method | URL | What it does |
| --- | --- | --- |
| `GET` | `/api/products/` | List your business's products (paginated, 20 per page: `?page=2`) |
| `POST` | `/api/products/` | Create a product |
| `GET` | `/api/products/{id}/` | Get a product |
| `PUT` / `PATCH` | `/api/products/{id}/` | Replace / partially update a product |
| `DELETE` | `/api/products/{id}/` | Delete a product |
| `GET` / `POST` | `/api/faqs/` | List / create FAQs |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/faqs/{id}/` | Get / replace / update / delete an FAQ |
| `GET` | `/api/businesses/{business_id}/products/` | List **all** products of a business, including inactive ones (paginated) |
| `GET` | `/api/businesses/{business_id}/faqs/` | List all FAQs of a business (paginated) |
| `GET` | `/api/configuration/random-number/` | Sample endpoint (public, no login needed) |
| `POST` | `/api/chat/` | `{prompt}` → `{reply, model, options}`: one-off chat with the local LLM (public, no login needed) |
| `GET` | `/api/chat/configuration/` | Your business's chat configuration `{id, business, config_json, last_updated}`. 404 if it has none yet |
| `GET` / `POST` | `/api/chat/sandbox-sessions/` | List / start your business's sandbox (test) chat sessions |
| `DELETE` | `/api/chat/sandbox-sessions/{id}/` | Delete one of your sandbox chat sessions |
| `POST` | `/api/chat/sandbox-sessions/{id}/messages/` | `{message}` → the assistant's reply, in one of your sandbox chat sessions |
| `GET` | `/api/chat/sessions/` | Your business's chat sessions (real ones by default; `sandbox=include` or `only` for test chats), with filters, sorting and pagination. See [Chat sessions](#chat-sessions) |
| `POST` | `/api/chat/sessions/messages/` | `{business_id, phone_number, message}` → the assistant's reply. Public (no login), for the Chat Sandbox / future webhook. See [Chat sessions](#chat-sessions) |
| `POST` | `/api/chat/sessions/` | `{phone_number, display_name}` → the new chat session (201). See [Chat sessions](#chat-sessions) |
| `PUT` | `/api/chat/configuration/` | `{config_json}`: replace your business's chat flow (validated). Creates it (201) if missing, otherwise 200 |
| `GET` | `/api/orders/` | Your business's orders, newest first, with filters, sorting and pagination. Read only. See [Orders](#orders) |
| `GET` | `/api/orders/{id}/` | One of your orders (403 another business's, 404 unknown) |

### Chat (temporary)

`chat_app` is a temporary copy of `../messaging-service`'s `/chat` endpoint, living here until that service has its own database. It needs [Ollama](https://ollama.com/) running on `http://localhost:11434` with the model pulled (`ollama pull qwen2.5:7b-instruct-q4_K_M`).

- Every request is independent: the fixed system prompt plus your `prompt` (≤4,000 characters). No history is kept.
- The model, system prompt and sampling options (`seed`, `temperature`, `num_predict` (max tokens), `top_k`, `top_p`, `min_p`, `repeat_penalty`, `repeat_last_n`, `presence_penalty`, `frequency_penalty`, `num_ctx`) are hardcoded in `chat_app/llm.py`.
- The seed is fixed (`42`), so the same prompt gives the same reply, which is handy for testing.
- Errors: 400 invalid prompt, 502 Ollama error (e.g. model not pulled), 503 Ollama not reachable, 504 Ollama timed out.

### Chat configuration

Each business has at most one chat configuration. Both endpoints need a login and work on **your own** business, so there's no ID in the URL. Users without a business (e.g. `superuser`) get 403. `PUT` only changes `config_json`; `id`, `business` and `last_updated` are read-only. An invalid `config_json` returns 400 with every problem listed under `config_json` (see the rules under [Data model](#data-model)). The sample data gives `kopi_owner`'s and `bloom_owner`'s businesses a configuration; FitLab starts with none.

### Chat sessions

`POST /api/chat/sessions/` (login required) starts a chat session between **your** business and a customer. Send `phone_number` (international format, e.g. `+6591234567`) and optionally `display_name`. The backend fills in the rest:

- `business`: your business.
- `created_time` and `last_chat_time`: now (the same instant).
- `chat_message_json`: `[]`.
- `chat_state_id`: the `id` of the Start block in your business's chat configuration.

Errors: 400 for an invalid phone number, a phone number that already has a session with your business, or a business with no chat configuration yet (set up the workflow first). 403 if your account isn't linked to a business.

`GET /api/chat/sessions/` (login required) lists your business's sessions, including each conversation. By default only real customer chats; `frontend-app`'s Chats tab uses it. All query parameters are optional and combine:

| Parameter | What it does |
| --- | --- |
| `sandbox` | `exclude` (default: real customer chats only), `include` (real and sandbox chats) or `only` (sandbox chats only) |
| `phone_number` | Exact phone number, e.g. `%2B6591234567` (URL-encode the `+`) |
| `search` | Case-insensitive text in the display name or phone number |
| `display_name` | Case-insensitive text in the display name |
| `chat_state_id` | The flow block the customer is at, e.g. `2` |
| `has_messages` | `true` (at least one message) or `false` (none yet) |
| `created_time_after`, `created_time_before` | Created in this range (ISO 8601, inclusive), e.g. `2026-09-08T00:00:00%2B08:00` |
| `last_chat_time_after`, `last_chat_time_before` | Last message in this range |
| `ordering` | Sort by `last_chat_time`, `created_time`, `display_name`, `phone_number` or `id`; `-` for descending; comma-separate several (e.g. `display_name,-created_time`). Default: `-last_chat_time` |
| `page` | Page number, from 1 |
| `page_size` | Items per page: default 20, max 100 |

The response is `{count, total_pages, current_page, page_size, has_next, has_previous, next, previous, results}`. An invalid filter or sort value returns 400, and a page past the end returns 404. Example: `/api/chat/sessions/?search=tan&ordering=display_name&page_size=10&page=1`.

`POST /api/chat/sessions/messages/` is how a **customer** sends a message. It needs no login, and will become the WhatsApp webhook later. (The Chat Sandbox uses the sandbox message endpoint above instead.) Send `{business_id, phone_number, message}`. It:

1. Finds that business's session for that phone number (404 if there isn't one; create it first with `POST /api/chat/sessions/`).
2. Appends the message as `{message, sent_by: "customer", message_time: now}` and sets `last_chat_time` to now.
3. Runs the [chat flow](#chat-flow): may move `chat_state_id` on to the next block and update `chat_state_data`.
4. Asks the LLM for a reply, with the current block's prompt and the conversation so far.
5. Appends the reply as `{message, sent_by: "business-automated", message_time: now}`, sets `last_chat_time` again, and returns that reply object.

If Ollama fails (502/503/504), the customer's message is still saved, but there's no reply.

### Chat flow

Each customer message (real or sandbox) moves the chat through the business's chat configuration (`chat_app/flow.py`). It needs Ollama, like the [one-off chat](#chat-temporary).

1. **Where is the chat?** The block whose `id` is the session's `chat_state_id`. If there's none (e.g. the block was deleted from the workflow), the Start block.
2. **Extract.** The LLM reads the conversation and returns JSON in the block type's format (Ollama structured output, `temperature` 0). The prompts and formats are in `chat_app/prompts.py`:

   | Block type | Goal | The LLM returns |
   | --- | --- | --- |
   | `START_BLOCK` | Welcome the customer, answer questions, find out if they want to order | `{"wants_to_order": true/false}` |
   | `PRODUCT_SELECTION_BLOCK` | Which products, and how many of each, confirmed as everything the customer wants | `{"items": [{"product_id", "quantity"}], "done_choosing": true/false}` |
   | `DETAILS_COLLECTION_BLOCK` | The details in the block's `fields` (default: name and email) | One key per field, e.g. `{"name": …/null, "postal_code": 238801/null}` (numbers as numbers) |
   | `CONFIRMATION_BLOCK` | Show the summary, get a confirmation | `{"decision": "confirm"/"change"/"none"}` |
   | `SEND_MESSAGE_BLOCK` | Send the block's fixed `message` | Nothing: no LLM call (see below) |

3. **Check deterministically** (in Python, not the LLM) whether that completes the block, and save what's valid in `chat_state_data`:
   - Start: complete when `wants_to_order` is true.
   - Product selection: every chosen product must be one of the business's active products, with a quantity from 1 up to `quantity_available`. Otherwise it stays, and the problem (e.g. "Only 3 Kaya Toast Set are available", or that a sold-out product "has run out") goes into the reply prompt. The cart is checked again on every message, so an item that sold out (or has less stock left) since it was chosen is removed, and the customer can't move on with it. The reply prompt says never to offer sold-out products. Then it **pauses**: the assistant recaps the order (items, quantities, prices, total) and asks whether the customer wants anything else. It completes only when the customer says that's everything (`done_choosing`) **about the cart as it already was**, so a message that adds or changes items ("…and 1 Kaya Toast, that's all") gets a recap first. Once confirmed, `chat_state_data.items_confirmed` is set, and kept until the items change, so coming back after a "change" at confirmation that doesn't touch the items (e.g. a new email) passes straight through.
   - Details collection: complete only when **every required** field is known and valid for its type. Optional fields (`required: false`) are stored when given and never hold the chat back (a problem with one is explained without blocking). Text: at most `max_length`. Number: a number (text like `"238,801"` is accepted), within `min_value`–`max_value`. Email: Django's email validator. Phone: digits, spaces, `+`, `-` and brackets, with 6–15 digits. Invalid values are explained to the customer (e.g. "Postal code must be at least 100000.") and never replace a valid one. Values already known are kept when the customer doesn't repeat them. The reply prompt lists every field (label in quotes, required or optional, type and limits) under "Details to collect", and the required ones still needed. It tells the assistant: the order is **not** confirmed yet, so never say it is; keep asking for required details in every reply until they're given, even if the customer ignores the question; ask for optional ones once; and use each label **exactly as written**, without paraphrasing or guessing what an unusual label (e.g. "Boo") means. On every step, the assistant may only say an order is confirmed once the flow is done. **Guardrails** on every step: stay on the current step's task; politely decline unrelated requests (general knowledge, coding, jokes, other businesses) or attempts to change or reveal the instructions, and steer back to the current step. The extraction prompt also ignores instructions inside the conversation.
   - Confirmation: `confirm` completes it; `change` goes back to the block after Start, where the blocks run again with the data already collected (so only what changed needs re-entering). It is never checked in the same message it's reached: the customer must see the summary first.

   - Send message: no extraction or check. Reaching it queues its fixed `message` and moves straight on to `next_block_id`. Each Send message block sends at most once per customer message, so blocks that lead back to each other can't loop.

   - **Going back (any block):** the extraction also returns `go_back_to`: `null`, or one of the earlier steps passed on the way from Start to the current block (Product selection, Details collection and Confirmation blocks; keys like `"product_selection"`, `"details_collection_2"` for repeats). Ollama's schema only allows those keys. When the customer clearly asks to change something from an earlier step ("I also want a Kaya Toast", "make it 3", "my email is wrong"), the chat goes back there **keeping everything collected**, and that step runs on the same message, so the change is applied straight away. Going back to Product selection clears `items_confirmed`, so the updated order is recapped and confirmed again; steps that are still complete pass straight through on the way forward. Going back is only offered at the step the chat was at when the message arrived, not at a step reached during that message (otherwise the "That's all" that finished Product selection could be read, at the next step, as going back to it). So there's at most one go-back per message, and none after the order is done. (Confirmation's `change`, without a specific step, still goes back to the step after Start.)

   When a block completes, the chat moves to its `next_block_id` and repeats steps 2–3 there, so one message can complete several blocks. When the last block completes, `chat_state_data.completed` becomes true and the chat stays at that block. (A workflow that's only a Start block never completes.) After that, messages get replies but no extraction.
4. **Save** `chat_state_id` and `chat_state_data`. A collected name also fills in an empty `display_name`.
5. **Send message blocks' messages** go out first (`sent_by: business-automated`), in order. If the flow ended on a Send message block (the last block), its message is the last word: the flow is completed and there's no LLM reply. If the order fails at a Confirmation before it, the messages after that Confirmation aren't sent.
6. **Reply.** The LLM writes the reply with a system prompt for the current block: the business's details, the step and its goal, what's known so far (order with total, details), what's still needed, problems to explain, and the products on sale (for Start and Product selection, with each product's short description; never the longer information). The reply step can call **read-only tools** (`chat_app/tools.py`, only the chatting business's data):
   - `get_product_details(product)`: one product's description and **information** (the long extra details), price and stock, by name (any case; a partial name works if it matches one product) or id. Ambiguous names list the matches; unknown names list what's on sale; inactive products are "not on sale at the moment".
   - `list_products`: every active product, with its description (not the information).
   - `list_faqs`: the business's FAQs.

   The prompt tells the assistant to answer "what is it?" with the product's description, to look other product questions up with `get_product_details` (answering the question rather than reciting the information) and business questions with `list_faqs`, to answer only from what it finds, and otherwise to **say honestly that it doesn't know** (offering to check with the team) rather than make anything up.

A message makes 2 or more LLM calls: one extraction per block it passes through, plus the reply (plus tool calls). Only the last 20 messages are sent (`HISTORY_MAX_MESSAGES`).

### Sandbox chat sessions

Test chats a business starts itself (e.g. from the Chat Sandbox), separate from real customer chats. All four endpoints need a login and only work on **your own** business (403 without a business).

- `GET /api/chat/sandbox-sessions/`: your sandbox sessions, paginated, most recent chat first.
- `POST /api/chat/sandbox-sessions/`: `{display_name?, phone_number?}`, both optional. Starts a sandbox session the same way as a real one (Start block, no messages, `created_time = last_chat_time = now`), so your business needs a chat configuration (400 otherwise). A business can have any number.
- `DELETE /api/chat/sandbox-sessions/{id}/`: deletes the session and its conversation (204). Another business's session → 403; a real customer session → 400 ("Only sandbox chat sessions can be deleted here."); unknown ID → 404.
- `POST /api/chat/sandbox-sessions/{id}/messages/`: `{message}`. Same flow as the customer message endpoint above (save the message as `customer`, run the [chat flow](#chat-flow), save and return the `business-automated` reply; the message is kept if the LLM fails), with the same 403/400/404 rules as delete. `frontend-app`'s Chat Sandbox uses this. For debugging, the response also has `debug` (not stored): the state before and after, each block's extraction (prompt, the LLM's JSON, the check result: complete / missing / issues), why the flow stopped, the reply system prompt, any tool calls and the Send message blocks' messages.

Sandbox sessions are left out of `GET /api/chat/sessions/` unless you ask for them with `sandbox=include` or `sandbox=only`, and `POST /api/chat/sessions/messages/` only finds real sessions.

### Orders

When a customer confirms at the Confirmation block (a real or sandbox chat), the [chat flow](#chat-flow) calls `checkout_app.services.place_order()`, which creates an `OrderItem` (`pending_payment`) and **reserves the stock**: each product's `quantity_available` goes down and `quantity_on_hold` goes up by the quantity. (Moving it on to `quantity_sold` is for the payment step, later.) The chat's `chat_state_data` gets `order_id`, and the reply gives the customer the order number.

- **All or nothing, safe under concurrency.** It runs in one transaction with the chat session's row locked. The product rows are locked with `SELECT … FOR UPDATE`, in id order so two orders can't deadlock. Stock is checked again (still on sale, enough left), and each update is guarded with `quantity_available >= quantity`, so stock can't go negative even on SQLite (which ignores `FOR UPDATE` and locks the whole database instead).
- **If it fails** (e.g. another customer bought the last ones since this customer chose, or the product was deactivated), nothing changes: no order, no stock change, and the chat stays at Confirmation with the problem in the reply ("Only 2 Kopi C are left."), so the customer can change their order.
- The price is the one the customer was shown when choosing (it isn't re-read). Later messages in the same chat don't order again.
- Sandbox chats place orders too, flagged `is_sandbox`, and they reserve stock like real ones.

`GET /api/orders/` (login required) lists your business's orders, newest first, **including sandbox orders** (they hold real stock). Each has `order_data`, `order_status`, `total` (computed) and the `chat_session` it came from. Optional parameters: `order_status`, `sandbox` (`include` (default), `exclude` or `only`), `created_time_after` / `created_time_before`, `ordering` (`created_time`, `order_status` or `id`; `-` for descending), `page` and `page_size` (max 100). The response is paginated like chat sessions. `GET /api/orders/{id}/` returns one order. Orders are read only for now (no create, edit or delete: 405).

### Access rules

- **Not logged in:** `401 Unauthorized`.
- **Business scope:** you only see and change records of **your own business** (the `business` on your user).
  - Lists only include your business's records.
  - Opening, editing or deleting another business's record returns **`403 Forbidden`**.
  - `business` is optional when creating; it defaults to your business. Sending another business's ID, whether on create or when trying to move a record, returns **`403 Forbidden`**.
  - Users without a business, like `superuser`, can view lists (which are empty) but get `403` for everything else.
- **Listing by business ID** (`/api/businesses/{business_id}/…`) is read-only. The checks run in this order:
  1. Not logged in: `401`.
  2. No business with that ID: `400`, with `{"business_id": ["Business configuration with ID 999 does not exist."]}`.
  3. Not your business (or your account has none): `403`.
  4. Otherwise: `200` with the paginated list.

  A non-numeric ID such as `/api/businesses/abc/products/` doesn't match the URL, so it returns `404`.
- **`quantity_sold` is read-only.** It's returned in responses, but sending it in a create or update returns `400 Bad Request`.
- **Validation errors return `400`** with a message per field, for example:
  - a negative quantity or price
  - a quantity over 1,000,000
  - a price with more than 2 decimal places
  - a name over 150 characters or an FAQ answer over 10,000 characters
  - a blank name
  - a product name or FAQ question that's already used in the same business

  The full list of rules is in [Data model](#data-model).

### Trying the APIs in Swagger UI

1. Start the server and open <http://127.0.0.1:8000/api/docs/>.
2. Click **Authorize** (top right) and log in one of two ways:
   - **basicAuth** (quickest): enter a username and password, e.g. `kopi_owner` / `123`.
   - **jwtAuth** (what `frontend-app` uses):
     1. Run `POST /api/auth/token/` with `{"username": "kopi_owner", "password": "123"}`.
     2. Copy the `access` value from the response.
     3. Paste it into **jwtAuth**, without the `Bearer ` prefix; Swagger adds it.
   Then click **Authorize** → **Close**.
3. Expand an endpoint, click **Try it out**, fill in the request and click **Execute**. For example, `GET /api/auth/me/` shows who you're logged in as and your business ID.

To switch user, click **Authorize** → **Logout** and log in as someone else (e.g. `bloom_owner`). Then try opening a Kopi & Co. product, such as `GET /api/products/1/`, to see the `403`.

You can also use your Django Admin login instead (**cookieAuth**). If you're logged in at `/admin/` in the same browser, Swagger requests use that session automatically. Business users can't log in to Admin, though, so basicAuth is the easiest way to test as them.

> [!NOTE]
> Username/password (Basic) authentication is only enabled while `DJANGO_DEBUG` is on, because it sends the password with every request. Use JWT everywhere else.

## Useful URLs (once the server is running)

| URL | What it is |
| --- | --- |
| <http://127.0.0.1:8000/api/docs/> | Swagger UI (interactive API docs) |
| <http://127.0.0.1:8000/api/redoc/> | ReDoc (alternative API docs) |
| <http://127.0.0.1:8000/api/schema/> | Raw OpenAPI 3 schema (YAML; add `?format=json` for JSON) |
| <http://127.0.0.1:8000/admin/> | Django admin |
| <http://127.0.0.1:8000/api/configuration/random-number/> | Sample endpoint: returns `{"value": <1–10>}`. `frontend-app`'s Home tab calls it. |

## Common commands

| Command | What it does |
| --- | --- |
| `python manage.py runserver` | Starts the dev server with auto-reload |
| `python manage.py makemigrations` | Creates migration files after you change models |
| `python manage.py migrate` | Applies migrations to the database |
| `python manage.py createsuperuser` | Creates an admin user |
| `python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions sample_order_items` | Loads the sample data |
| `python manage.py flush --noinput` | Deletes all rows from every table (keeps the tables); see [Resetting the local database](#resetting-the-local-database) |
| `python manage.py test` | Runs all tests (see [Running tests](#running-tests)) |
| `python manage.py check` | Checks the project configuration for problems |
| `python manage.py spectacular --validate --file schema.yml` | Exports and validates the OpenAPI schema |

## Running tests

With the virtual environment active, from `configuration-service/`:

```bash
python manage.py test                      # run all tests
python manage.py test product_app          # one app
python manage.py test product_app.test_api # just the product/FAQ API tests
python manage.py test -v 2                 # verbose: list each test
```

Tests use a temporary database, so your `db.sqlite3` isn't touched.

| File | Covers |
| --- | --- |
| `auth_app/test_api.py` | JWT login, refresh + rotation, verify, logout (blacklist), `/api/auth/me/`, CORS for the `Authorization` header |
| `product_app/test_api.py` | Product and FAQ APIs: login required, business scoping and 403s, CRUD, read-only `quantity_sold`, validation; list-by-business endpoints (200 / 400 unknown ID / 401 / 403 other business, pagination, read-only) |
| `product_app/tests.py` | Product and FAQ model validation and database constraints (including the description and information limits); sample products and FAQs are valid; migration `0003` moves long descriptions into `information` |
| `auth_app/tests.py` | `BusinessUser` model, Django Admin pages load |
| `configuration_app/tests.py` | `BusinessConfiguration` model, random-number endpoint, CORS |
| `chat_app/tests/test_models.py` | `validate_chat_config` (including Details collection `fields`), `validate_chat_messages` and `validate_chat_state_data` rules; `ChatConfiguration` and `ChatSession` models (validation, uniqueness, `chat_state_id` must match a block); sample fixtures are valid |
| `chat_app/tests/test_api.py` | Chat endpoint returns the reply, with the LLM mocked (no Ollama needed); chat configuration GET/PUT (401/403/404, create vs update, read-only fields, saving Details collection `fields`, invalid `config_json` → 400); chat sessions create/list (filters, sorting and pagination on the sample fixtures) and customer messages (LLM mocked); sandbox sessions list/create/delete (only sandbox, only your business) |
| `chat_app/tests/test_tools.py` | The reply step's tools: `get_product_details` (description + information; name in any case, partial name, id, ambiguous names, no description or information, inactive / unknown / another business's products, bad arguments), `list_products` (no information), `list_faqs`, unknown tools; descriptions in the prompt's catalog |
| `chat_app/tests/test_flow.py` | The chat flow (LLM mocked): a whole conversation from Start to confirmed, going back on "change", invalid choices, unknown state → Start block, tool calls, invalid JSON → 502; custom Details collection fields (asks for every field, only moves on when all are valid); going back to an earlier step from any block (keeps data, one per message, `go_back_targets`); confirming places an order and reserves stock (once), and a product sold out since it was chosen undoes the confirmation; each block's deterministic check and each detail type's value check |
| `checkout_app/tests/test_models.py` | `validate_order_data` rules; `OrderItem` defaults (`pending_payment`), statuses (also the database constraint), total; sample fixture is valid |
| `checkout_app/tests/test_services.py` | `place_order`: creates the order and reserves stock; all or nothing when any item fails (sold out, inactive, another business's or deleted product); can't oversell; a simulated lost race is stopped by the guarded update and rolled back; product rows locked in id order |
| `checkout_app/tests/test_api.py` | Orders list/detail: 401, 403 (no business, another business's order), 404 (unknown order, page past the end), 405 (read only), filters, sorting, pagination |

### Resetting the local database

To put the data back to the sample state, delete every row (the tables and migrations stay) and reload the fixtures:

```bash
python manage.py flush --noinput
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions sample_order_items
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com
```

> [!WARNING]
> `flush` deletes **all** rows in every table: your own records, the superuser, sessions and blacklisted tokens. Drop `--noinput` to get a confirmation prompt first. Existing JWT tokens stop working, because their users no longer exist until the fixtures are reloaded (and anyone logged in has to log in again).

To delete the database file itself and rebuild it from the migrations (e.g. after migration problems):

```bash
rm db.sqlite3
python manage.py migrate
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_chat_configurations sample_chat_sessions sample_order_items
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com
```

> [!IMPORTANT]
> If your `db.sqlite3` was created before the custom user model (`BusinessUser`) was added, `migrate` fails with an `InconsistentMigrationHistory` error. Reset the database as shown above.

## Configuration (environment variables)

`config/settings.py` reads the variables below. The defaults work for local development, so you don't need to set anything to get started. See `.env.example` for a template. The file isn't loaded automatically; export the variables in your shell, for example `export DJANGO_DEBUG=False`.

| Variable | Default | Description |
| --- | --- | --- |
| `DJANGO_DEBUG` | `True` | Debug mode. Set to `False` outside local development. |
| `DJANGO_SECRET_KEY` | insecure dev key (only when `DEBUG` is on) | Must be set when `DEBUG` is off. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames the server responds to. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated origins allowed to call the API from a browser. The default is the `frontend-app` Vite dev server. |
| `DJANGO_DB_ENGINE` | `sqlite` | `sqlite` (`db.sqlite3`, for running without Docker) or `postgresql` (used by `docker-compose.yml`). |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | `configuration_service`, `postgres`, empty, `localhost`, `5432` | The PostgreSQL connection, when `DJANGO_DB_ENGINE=postgresql`. |
| `OLLAMA_HOST` | `http://localhost:11434` | The Ollama server for chat (Docker uses `http://host.docker.internal:11434`, the host machine). |

## Connecting from frontend-app

`frontend-app` (Vite, <http://localhost:5173>) calls this service from the browser, so CORS must allow its origin:

- `corsheaders.middleware.CorsMiddleware` is the **first** entry in `MIDDLEWARE`. That way every response, including redirects and errors produced by later middleware, carries CORS headers.
- `CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173` and `http://127.0.0.1:5173`. For other frontend URLs (e.g. a deployed site), set `DJANGO_CORS_ALLOWED_ORIGINS`.
- `CORS_URLS_REGEX` limits CORS headers to `/api/` routes.

To try it, run `python manage.py runserver` here and `npm run dev` in `../frontend-app`, then open <http://localhost:5173>.

## Project structure

```
configuration-service/
├── config/                 # Django project: settings, root URLs, WSGI/ASGI entry points
│   ├── settings.py
│   ├── urls.py             # /admin, /api/configuration, /api/products, /api/faqs, /api/chat, /api/schema, /api/docs, /api/redoc
│   ├── asgi.py
│   └── wsgi.py
├── configuration_app/      # Businesses (BusinessConfiguration) + sample API
│   ├── fixtures/           # sample_business_configurations.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py
│   ├── serializers.py      # DRF serializers
│   ├── tests.py            # Endpoint, CORS and model tests
│   ├── urls.py             # App routes, mounted at /api/configuration/
│   └── views.py            # RandomNumberView
├── auth_app/               # Custom user model (BusinessUser)
│   ├── fixtures/           # sample_business_users.json
│   ├── migrations/
│   ├── admin.py            # BusinessUserAdmin (extends Django's UserAdmin)
│   ├── serializers.py      # MeSerializer
│   ├── views.py            # Login/refresh/verify/logout (SimpleJWT) + MeView
│   ├── urls.py             # /api/auth/…
│   ├── test_api.py         # Auth API tests
│   ├── business_scope.py   # Business-ownership permission + serializer/viewset mixins
│   ├── models.py
│   └── tests.py            # Model + admin smoke tests
├── product_app/            # Products and FAQs
│   ├── fixtures/           # sample_products.json, sample_faqs.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py
│   ├── serializers.py      # ProductSerializer, FAQSerializer
│   ├── views.py            # ProductViewSet, FAQViewSet, BusinessProductListView, BusinessFAQListView
│   ├── urls.py             # /api/products/, /api/faqs/, /api/businesses/{id}/products|faqs/
│   ├── tests.py            # Model validation tests
│   └── test_api.py         # API tests
├── chat_app/               # ChatConfiguration (chat flow) + temporary one-off chat with the local LLM (Ollama)
│   ├── fixtures/           # sample_chat_configurations.json, sample_chat_sessions.json
│   ├── migrations/
│   ├── admin.py
│   ├── constants.py        # BLOCK_TYPES, MESSAGE_SENDERS, DETAIL_FIELD_TYPES, DEFAULT_DETAIL_FIELDS
│   ├── models.py           # ChatConfiguration, ChatSession
│   ├── validators.py       # validate_chat_config, validate_chat_messages, validate_chat_state_data
│   ├── llm.py              # Ollama client, model, sampling options; structured output + tool-calling helpers
│   ├── flow.py             # The chat flow: extraction → deterministic checks → state → reply
│   ├── prompts.py          # Per-block-type goals, extraction prompts + JSON schemas, reply prompts
│   ├── tools.py            # Read-only tools for the reply step (get_product_details, list_products, list_faqs)
│   ├── serializers.py      # Chat request/response, ChatConfigurationSerializer
│   ├── views.py            # ChatView, ChatConfigurationView
│   ├── urls.py             # /api/chat/, /api/chat/configuration/
│   └── tests/
│       ├── test_models.py  # Validator + model tests
│       ├── test_api.py     # Chat API (mocked LLM) + chat configuration API tests
│       └── test_flow.py    # Chat flow tests (mocked LLM)
├── checkout_app/           # Orders placed when customers confirm in a chat
│   ├── fixtures/           # sample_order_items.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py           # OrderItem, OrderStatus
│   ├── validators.py       # validate_order_data
│   ├── services.py         # place_order(): creates the order + reserves stock (locked, all or nothing)
│   ├── serializers.py      # OrderItemSerializer (read only)
│   ├── filters.py          # OrderItemFilter
│   ├── views.py            # OrderItemListView, OrderItemDetailView
│   ├── urls.py             # /api/orders/, /api/orders/{id}/
│   └── tests/              # test_models.py, test_services.py, test_api.py
├── manage.py
├── requirements.txt
└── .env.example
```

## Adding an endpoint (quick guide)

1. Define a model in the right app's `models.py`, then run `python manage.py makemigrations` and `python manage.py migrate`.
2. Add a serializer to the app's `serializers.py`.
3. Create a view or viewset in the app's `views.py`.
4. Register the route in the app's `urls.py`. For a new app, also `include()` its URLs in `config/urls.py` under `/api/`.

The endpoint then appears in Swagger UI at `/api/docs/` automatically.
