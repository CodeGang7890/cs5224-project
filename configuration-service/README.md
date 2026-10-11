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
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions

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
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions
```

| Fixture | File | Contents |
| --- | --- | --- |
| `sample_business_configurations` | `configuration_app/fixtures/` | 5 businesses: Kopi & Co. Café (a small business for testing), Bloom & Twine Florist Studio (sells flowers: products only), FitLab Personal Training, Lumen & Lens Photography Studio (photo sessions as services, and prints and frames delivered as products), Rally Point Courts (2 badminton and 2 tennis courts, rented by the hour: services only) |
| `sample_business_users` | `auth_app/fixtures/` | 6 business users linked to those businesses |
| `sample_products` | `product_app/fixtures/` | 29 products (one of them inactive). Lumen & Lens Photography Studio has 10 (prints, a canvas, frames, an album, an acrylic block; $18 to $240), made to order from your gallery and delivered anywhere in Singapore. Each has a short description and longer information. Bloom & Twine Florist Studio has 12 realistic products across fresh, dried / preserved, soap and crochet flowers ($5.90 to $288; one sold out, and one down to its last piece), each with detailed information about the product itself (what's in it, size, how long it lasts, care, allergies and pets), with no prices, variants or logistics. Bloom is self-collection only: it doesn't deliver. Kopi & Co. Café's 5 have long, detailed information (ingredients, sizes, options, allergens, storage, and a few product FAQs) for testing `get_product_details`, with some details deliberately left out to test "I don't know" |
| `sample_services` | `product_app/fixtures/` | Lumen & Lens Photography Studio's 2 photographers (service providers Mei Lin and Arjun) and 8 services (portrait, couple, family, newborn, maternity, graduation, corporate headshots, pets; 30 minutes to 3 hours, $150 to $480), each linked to the photographers who do it; Rally Point Courts's 4 courts (Badminton Court 1 and 2, indoor; Tennis Court 1 and 2, outdoor) and 2 services (Badminton Court (1 hour) $20, Tennis Court (1 hour) $32; starting on the hour). Every provider has 13 weeks of availability (7 Sep to the week of 30 Nov 2026), with the bookings already marked: the courts are open 9am to 9pm every day |
| `sample_faqs` | `product_app/fixtures/` | 52 FAQs: 10 for Lumen & Lens Photography Studio (location, payment, changes, delivery of photos, outfits, locations, delivering prints, prints of other photos, damaged prints, collecting prints), 8 for Rally Point Courts (hours, booking length, no equipment rental (bring your own), indoor / outdoor, rain, cancellations, parking and showers, payment), and 12 for Kopi & Co. Café (hours, reservations, halal, delivery, payment, vegetarian options, sugar levels, catering, parking, Wi-Fi, pets, cancellations), 20 for Bloom & Twine Florist Studio (2 of them from answered questions; self-collection only: where and when to collect, same-day collection, collecting for someone else, hours, payment, care, card messages, cancellations, substitutions, corporate, weddings, workshops, allergies and pets…), 2 for FitLab |
| `sample_chat_configurations` | `chat_app/fixtures/` | 4 configurations: Kopi & Co. Café (orders ask for name, email and pickup time), Bloom & Twine Florist Studio (name, card message and collection date), Lumen & Lens (orders ask for name, email, the photos to print and a delivery address; bookings for name, number of people and optional notes) and Rally Point Courts (bookings ask for name, email and an optional number of players; with a welcome message and the casual style) |
| `sample_chat_sessions` | `chat_app/fixtures/` | 17 customer chats: 11 with Kopi & Co. Café (at different steps of its flow, over 1–12 Sep, one with no messages yet), 5 with Bloom & Twine Florist Studio (one choosing products, one giving details, and three where customers asked things the FAQs don't cover), 1 with FitLab, 1 with Lumen & Lens (a customer booking a family shoot through the chat). `+6591234567` chats with both the café and the florist. Plus 2 sandbox (test) chats for Kopi & Co. Café, one without a phone number |
| `sample_unanswered_questions` | `chat_app/fixtures/` | 5 questions Bloom & Twine Florist Studio's customers asked that the assistant couldn't answer: 2 answered (now FAQs, with the answer in the chat), 2 open (waiting for the owner) and 1 dismissed |
| `sample_schedule_items` | `checkout_app/fixtures/` | 1,019 bookings from 7 Sep to 30 Nov 2026: 33 Lumen & Lens sessions (one from a sandbox chat, one made in the sample chat) and 986 court bookings at Rally Point Courts (busiest on weekday evenings and at weekends, often two back-to-back hours, many by regulars). Past ones (before 11 Oct 2026) are mostly completed; upcoming ones are paid or pending payment, fewer the further ahead |
| `sample_order_items` | `checkout_app/fixtures/` | 49 orders: 4 for Kopi & Co. Café (one per status, plus a pending sandbox order), 19 for Lumen & Lens Photography Studio (prints and frames delivered to Singapore addresses, 9 Sep to 11 Oct 2026) and 26 for Bloom & Twine Florist Studio (8 Aug to 12 Sep 2026: birthdays, anniversaries, a Teachers' Day rush, grand openings; mostly completed, the latest paid or pending payment). They aren't linked to chats. They count towards the products' quantities on hold and sold |

Every sample account uses the password **`123`**, so you can log in as anyone while testing:

| Username | Business | Can log in to |
| --- | --- | --- |
| `kopi_owner` | Kopi & Co. Café (1) | API only |
| `bloom_owner` | Bloom & Twine Florist Studio (2) | API only |
| `bloom_staff` | Bloom & Twine Florist Studio (2) | API only |
| `fitlab_owner` | FitLab Personal Training (3) | API only |
| `lumen_owner` | Lumen & Lens Photography Studio (4) | API only |
| `rally_owner` | Rally Point Courts (5) | API only |
| `superuser` (created by the `createsuperuser` command, not a fixture) | none | Django Admin (full access). Gets 403 on product/FAQ changes, because it has no business. |

Business users aren't staff, so they can't log in to Django Admin.

Notes:
- Fixtures use fixed IDs, so re-running `loaddata` resets those records to the sample values rather than creating duplicates. Records you created yourself are kept.
- Load them in one command, as shown above. The records depend on each other: users, products, FAQs, chat configurations and chat sessions point to businesses.
- `loaddata` saves records as-is, without running model validation. When you edit a fixture, keep the data within the model rules.

## Data model

| App | Model | Fields |
| --- | --- | --- |
| `configuration_app` | `BusinessConfiguration` | `id`, `business_name` (≤150 chars), `description` (≤2,000 chars, optional), `location` (≤255 chars) |
| `auth_app` | `BusinessUser` | Every field of Django's built-in user (username, password, email, first/last name, `is_staff`, `is_superuser`, `is_active`, groups, permissions, `last_login`, `date_joined`), plus `business` → `BusinessConfiguration` (optional) |
| `product_app` | `Product` | `id`, `business` → `BusinessConfiguration`, `name` (≤150 chars), `description` (≤300 chars, optional: the short summary the chat assistant gives customers), `information` (≤5,000 chars, optional: extra details the assistant looks up to answer specific questions; customers don't see it as is), `price` (≥0, 2 decimal places, up to 99,999,999.99), `total_quantity` (whole number ≥0, default 0: how many the business has in total, including those on hold or sold), `is_active` (default true). Also, worked out from the orders (not stored): `quantity_on_hold` (in orders pending payment or paid), `quantity_sold` (in completed orders) and `quantity_available` (total − on hold − sold) |
| `product_app` | `FAQ` | `id`, `business` → `BusinessConfiguration`, `question` (≤300 chars), `answer` (≤10,000 chars) |
| `product_app` | `ServiceProvider` | `id`, `business` → `BusinessConfiguration`, `name` (≤150 chars, unique per business: one photographer, teacher, venue…), `description` (≤300, optional), `is_active` |
| `product_app` | `WeeklyAvailability` | `id`, `service_provider` → `ServiceProvider`, `week` (its Monday; one per provider and week), `availability` (672 letters: one per 15-minute block of the week from Monday 00:00, local time: `O` available, `U` unavailable (the default), `H` on hold (booked, payment pending), `X` booked) |
| `product_app` | `Service` | `id`, `business` → `BusinessConfiguration`, `service_providers` (many-to-many → `ServiceProvider`: who can do it), `name` (≤150 chars), `description` (≤300), `information` (≤5,000), `price`, `duration_minutes` (15–1,440), `buffer_minutes` (0–1,440: blocked after each booking, without the customer), `start_interval_minutes` (15–1,440, default 15: bookings only start every this many minutes, counted from midnight, e.g. 30 → 9:00, 9:30…, 60 → on the hour), `is_active`. Minutes are multiples of 15 |
| `chat_app` | `ChatSession` | `id`, `business` → `BusinessConfiguration`, `phone_number` (the customer's, international format e.g. `+6591234567`), `display_name` (≤150 chars, optional), `created_time` (defaults to now), `last_chat_time`, `chat_message_json` (the conversation, see below), `chat_state_id` (the chat flow step the customer is at: `start`, `product_selection`, `details_collection` or `confirmation`; default `start`), `chat_state_data` (what the chat flow has collected so far, see below), `is_sandbox` (a test chat from the Chat Sandbox; default false) |
| `chat_app` | `ChatConfiguration` | `id`, `business` → `BusinessConfiguration` (one per business, optional), `product_detail_fields` and `schedule_detail_fields` (the customer details the chat asks for when ordering products and when booking a service, set separately, see below; each defaults to a required name and email), `welcome_message` (≤1,000 characters, sent as the reply to a chat's first message; blank: none; may use `{business_name}`), `reply_style` (`friendly` (default), `professional`, `casual`, `brief` or `custom`), `custom_style` (≤500 characters, your own description of the style; required with `custom`), `last_updated` (set automatically on every save) |
| `checkout_app` | `OrderItem` | `id`, `business` → `BusinessConfiguration`, `chat_session` → `ChatSession` (the chat it was placed in; cleared if the chat is deleted), `is_sandbox`, `order_data` (what was ordered and the customer details, see below), `order_status` (`pending_payment` (default), `payment_received` or `order_completed`), `created_time`, `updated_time` |
| `checkout_app` | `ScheduleItem` | A booked time slot: `id`, `business`, `chat_session`, `is_sandbox`, `service` and `service_provider` (both kept as null if deleted), `start_time`, `end_time` (start + duration), `blocked_until` (end + buffer), `schedule_data` (`{service: {service_id, name, price, duration_minutes, buffer_minutes}, details: {...}}`), `order_status` (like orders), `created_time`, `updated_time` |

**Service providers' weeks and bookings.** Each service provider has one weekly availability per week; a week without one is all unavailable. The business opens (`O`) and closes (`U`) blocks: in a week, for days and times over a range of weeks ("the next 2 weeks, Monday to Friday, 9am to 5pm"), or by copying a week. Bookings mark their own blocks, automatically: when a booking is made (pending payment) its blocks go from `O` to `H`, once it's paid or completed to `X`, and if it's deleted back to `O`; the buffer after it is marked too, where it was open. The business can't change `H` / `X` blocks. A service can start at one of its allowed start times (every `start_interval_minutes` from midnight: with 30, 9:00 or 9:30 but not 9:15), at least an hour ahead, if one of its active providers has the whole duration open (`O`) and nothing booked in the buffer. Blocks are local times in `DJANGO_SCHEDULE_TIME_ZONE` (default `Asia/Singapore`).

Rules enforced by Django validation (e.g. in Django Admin) **and** by the database:
- Price and quantities can't be negative.
- Business names, locations, product names, FAQ questions and FAQ answers can't be empty.
- Product names and FAQ questions must be unique **within a business**. Different businesses can reuse them.

The chat flow itself is fixed (see [Chat flow](#chat-flow)); `ChatConfiguration` only holds the settings of its steps. Among them, `product_detail_fields` and `schedule_detail_fields`: the customer details the Details collection step (product orders) and the Booking details step (service bookings) ask for, each its own list (set in the frontend's Workflow tab by clicking the Details collection block). A business that hasn't saved a configuration uses the defaults, name and email (`DEFAULT_DETAIL_FIELDS` in `chat_app/constants.py`). `chat_app/validators.py` (`validate_detail_fields`) checks it on every validated save, e.g. in Django Admin. Example:

```json
"product_detail_fields": [
  {"key": "name", "label": "Receiver name", "type": "text", "max_length": 150},
  {"key": "email", "label": "Email", "type": "email"},
  {"key": "postal_code", "label": "Postal code", "type": "number", "min_value": 100000, "max_value": 999999},
  {"key": "notes", "label": "Customisation notes", "type": "text", "max_length": 200, "description": "e.g. less sugar"}
]
```

- 1 to 20 fields. Each has `key`, `label` and `type`, and only the optional keys its type allows.
- `key`: lowercase letters, digits and underscores, starting with a letter, at most 40 characters, unique. The customer's answer is stored under it in `chat_state_data.details`.
- `label`: non-blank, at most 100 characters. It's what the assistant asks for.
- `type`: `text`, `number` or `email`. There's no phone type: customers chat on WhatsApp, so the chat already has their number.
- `description` (any type, optional): a hint for the assistant, at most 300 characters.
- `required` (any type, optional): `false` for an optional detail; missing means required. At least one field must be required (otherwise the step would move on before asking anything).
- `max_length` (`text` only, optional): 1–2,000 (default 500).
- `min_value` / `max_value` (`number` only, optional): numbers, minimum ≤ maximum.
- Every problem is listed.

`ChatSession` rules (checked by Django validation, e.g. in Django Admin):
- `phone_number` is required and unique **within a business** (both also enforced by the database). Different businesses can each have a chat with the same number.
- **Sandbox sessions** (`is_sandbox = true`) are exempt: the phone number is optional (still validated if given), may repeat, and a business can have any number of them.
- `chat_message_json` is a list of messages, oldest first: `{"message": "Hi", "sent_by": "customer", "message_time": "2026-09-01T09:00:00+08:00"}`. `validate_chat_messages` (`chat_app/validators.py`) checks that `message` is non-blank (≤4,096 chars), `sent_by` is `customer`, `business-manual` or `business-automated` (defined in `chat_app/constants.py`), and `message_time` is an ISO 8601 date-time with a timezone, in chronological order. An empty list is fine.
- `chat_state_id` is one of the chat flow's steps: `start` (no order in progress), `product_selection`, `details_collection` or `confirmation` (also enforced by the database).
- `chat_state_data` is an object; every key is optional (`{}` means nothing collected yet). `validate_chat_state_data` checks: `items`, a list of `{product_id, name, unit_price, quantity}` (the chosen products; `name` and `unit_price` are a snapshot, `unit_price` a decimal string like `"5.50"`, `quantity` ≥1); `items_confirmed`, true once the customer said those items are everything; `details`, the customer details collected so far by field key (non-blank strings or numbers, e.g. `{"name": "Alice", "postal_code": 238801}`); `last_order_id`, the last order placed in this chat (once an order is placed, the chat goes back to the start with only this). Example: `{"items": [{"product_id": 1, "name": "Kopi C", "unit_price": "1.80", "quantity": 2}], "details": {"name": "Alice"}}`.

`OrderItem.order_data` is `{"items": [...], "details": {...}}`, checked by `validate_order_data` (`checkout_app/validators.py`):
- `items`: at least one `{product_id, name, unit_price, quantity}`, one per product. `name` and `unit_price` are what the customer was shown (`unit_price` a decimal string like `"5.50"`: ≥0, at most 2 decimal places); `quantity` is 1–1,000,000.
- `details`: the customer details collected in the chat, by field key (non-blank strings or numbers). Can be empty (e.g. orders created in Django Admin).
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
| `GET` | `/api/chat/configuration/` | Your business's chat configuration `{id, business, product_detail_fields, schedule_detail_fields, welcome_message, reply_style, custom_style, last_updated}`; the defaults (with `id` null) if you haven't saved one |
| `GET` | `/api/chat/configuration/reply-styles/` | The reply styles to choose from: `{key, label, description, instructions}` (`instructions` null for `custom`) |
| `GET` / `POST` | `/api/chat/sandbox-sessions/` | List / start your business's sandbox (test) chat sessions |
| `DELETE` | `/api/chat/sandbox-sessions/{id}/` | Delete one of your sandbox chat sessions |
| `POST` | `/api/chat/sandbox-sessions/{id}/messages/` | `{message}` → the assistant's reply, in one of your sandbox chat sessions |
| `GET` | `/api/chat/sessions/` | Your business's chat sessions (real ones by default; `sandbox=include` or `only` for test chats), with filters, sorting and pagination. See [Chat sessions](#chat-sessions) |
| `POST` | `/api/chat/sessions/messages/` | `{business_id, phone_number, message}` → the assistant's reply. Public (no login), for the Chat Sandbox / future webhook. See [Chat sessions](#chat-sessions) |
| `POST` | `/api/chat/sessions/` | `{phone_number, display_name}` → the new chat session (201). See [Chat sessions](#chat-sessions) |
| `PUT` | `/api/chat/configuration/` | `{product_detail_fields?, schedule_detail_fields?, welcome_message?, reply_style?, custom_style?}`: replace the details your chat asks for (for orders, for bookings), and the welcome message and reply style (validated; left out = kept). Creates the configuration (201) if missing, otherwise 200 |
| `GET` / `POST` | `/api/service-providers/` | List / create your service providers (`GET` / `PUT` / `PATCH` / `DELETE` on `/{id}/`) |
| `GET` | `/api/service-providers/{id}/calendar/?week=YYYY-MM-DD` | A provider's week: its letters and the bookings in it (who booked, their details, status), for the calendar |
| `POST` | `/api/service-providers/{id}/slots/` | `{date_from, date_to, weekdays, time_from, time_to, available}`: open (or close) those days' times, e.g. the next 2 weeks Mon–Fri 09:00–17:00. Booked blocks are left alone |
| `POST` | `/api/service-providers/{id}/copy-week/` | `{source_week, target_week?, weeks?}`: copy a week's open / closed blocks to the next weeks |
| `GET` / `POST` | `/api/weekly-availabilities/` | List (filters `service_provider`, `week_after` / `week_before`) / create your providers' weeks (`GET` / `PUT` / `PATCH` / `DELETE` on `/{id}/`). Only `O` ↔ `U` can be changed; a week with bookings can't be deleted |
| `GET` / `POST` | `/api/services/` | List / create your services (`GET` / `PUT` / `PATCH` / `DELETE` on `/{id}/`); `service_providers` must be your own |
| `GET` | `/api/services/{id}/slots/?date_from=&date_to=` | Every start time the service can be booked at (at most 31 days) |
| `GET` | `/api/schedules/` | Your business's bookings (`ScheduleItem`), latest start first, with filters (`order_status`, `sandbox`, `service`, `service_provider`, `start_time_after` / `_before`, `ordering`) and pagination. Read only |
| `GET` | `/api/schedules/{id}/` | One of your bookings (403 another business's, 404 unknown) |
| `GET` | `/api/orders/` | Your business's orders, newest first, with filters, sorting and pagination. Read only. See [Orders](#orders) |
| `GET` | `/api/orders/{id}/` | One of your orders (403 another business's, 404 unknown) |

### Chat (temporary)

`chat_app` is a temporary copy of `../messaging-service`'s `/chat` endpoint, living here until that service has its own database. It needs [Ollama](https://ollama.com/) running on `http://localhost:11434` with the model pulled (`ollama pull qwen2.5:7b-instruct-q4_K_M`).

- Every request is independent: the fixed system prompt plus your `prompt` (≤4,000 characters). No history is kept.
- The model, system prompt and sampling options (`seed`, `temperature`, `num_predict` (max tokens), `top_k`, `top_p`, `min_p`, `repeat_penalty`, `repeat_last_n`, `presence_penalty`, `frequency_penalty`, `num_ctx` (8,192 tokens)) are hardcoded in `chat_app/llm.py`.
- The seed is fixed (`42`), so the same prompt gives the same reply, which is handy for testing.
- Errors: 400 invalid prompt, 502 Ollama error (e.g. model not pulled), 503 Ollama not reachable, 504 Ollama timed out.

### Chat configuration

The chat flow is fixed (see [Chat flow](#chat-flow)); the chat configuration holds the settings of its steps, such as the customer details the Details collection and Booking details steps ask for (`product_detail_fields`, `schedule_detail_fields`). Each business has at most one. Both endpoints need a login and work on **your own** business, so there's no ID in the URL. Users without a business (e.g. `superuser`) get 403. `GET` returns the defaults (name and email, with `id` and `last_updated` null) until your business saves its own. `PUT` changes the fields you send (the others are kept); `id`, `business` and `last_updated` are read-only. An invalid list returns 400 with every problem listed under its name (e.g. `product_detail_fields`) (see the rules under [Data model](#data-model)). The sample data gives `kopi_owner`'s and `bloom_owner`'s businesses a configuration; FitLab uses the defaults.

### Chat sessions

`POST /api/chat/sessions/` (login required) starts a chat session between **your** business and a customer. Send `phone_number` (international format, e.g. `+6591234567`) and optionally `display_name`. The backend fills in the rest:

- `business`: your business.
- `created_time` and `last_chat_time`: now (the same instant).
- `chat_message_json`: `[]`.
- `chat_state_id`: `start` (no order in progress), and `chat_state_data`: `{}`.

Errors: 400 for an invalid phone number, or a phone number that already has a session with your business. 403 if your account isn't linked to a business.

`GET /api/chat/sessions/` (login required) lists your business's sessions, including each conversation. By default only real customer chats; `frontend-app`'s Chats tab uses it. All query parameters are optional and combine:

| Parameter | What it does |
| --- | --- |
| `sandbox` | `exclude` (default: real customer chats only), `include` (real and sandbox chats) or `only` (sandbox chats only) |
| `phone_number` | Exact phone number, e.g. `%2B6591234567` (URL-encode the `+`) |
| `search` | Case-insensitive text in the display name or phone number |
| `display_name` | Case-insensitive text in the display name |
| `chat_state_id` | The chat flow step the customer is at: `start`, `product_selection`, `details_collection` or `confirmation` |
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
3. Runs the [chat flow](#chat-flow): the router decides what the message is about; the order steps may move `chat_state_id` on and update `chat_state_data`.
4. Asks the LLM for a reply, with a prompt describing what the flow found and the conversation so far.
5. Appends the reply as `{message, sent_by: "business-automated", message_time: now}`, sets `last_chat_time` again, and returns that reply object.

If Ollama fails (502/503/504), the customer's message is still saved, but there's no reply.

### Chat flow

The chat flow is the same for every business (`chat_app/flow.py`): a **router** decides what each customer message is about, and code sends it to the right handler. Businesses only configure the steps' settings (so far, the details to collect: see [Chat configuration](#chat-configuration)). It needs Ollama, like the [one-off chat](#chat-temporary).

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

### Sandbox chat sessions

Test chats a business starts itself (e.g. from the Chat Sandbox), separate from real customer chats. All four endpoints need a login and only work on **your own** business (403 without a business).

- `GET /api/chat/sandbox-sessions/`: your sandbox sessions, paginated, most recent chat first.
- `POST /api/chat/sandbox-sessions/`: `{display_name?, phone_number?}`, both optional. Starts a sandbox session the same way as a real one (`chat_state_id` `start`, no messages, `created_time = last_chat_time = now`). A business can have any number.
- `DELETE /api/chat/sandbox-sessions/{id}/`: deletes the session and its conversation (204). Another business's session → 403; a real customer session → 400 ("Only sandbox chat sessions can be deleted here."); unknown ID → 404.
- `POST /api/chat/sandbox-sessions/{id}/messages/`: `{message}`. Same flow as the customer message endpoint above (save the message as `customer`, run the [chat flow](#chat-flow), save and return the `business-automated` reply; the message is kept if the LLM fails), with the same 403/400/404 rules as delete. `frontend-app`'s Chat Sandbox uses this. For debugging, the response also has `debug` (not stored): the state before and after, the router's intents (and its prompt and JSON), each order step's extraction (prompt, the LLM's JSON, the check result: complete / missing / issues / go back), why the order steps stopped, the question check (if the router found a question), the reply system prompt and any tool calls.

Sandbox sessions are left out of `GET /api/chat/sessions/` unless you ask for them with `sandbox=include` or `sandbox=only`, and `POST /api/chat/sessions/messages/` only finds real sessions.

### Unanswered questions

When the [router](#chat-flow) finds a question in a customer message, it goes through a **question check**: one extra LLM call (JSON, temperature 0) that sees the business's description, FAQs, products on sale and the full information of any product the message mentions, and decides whether the message is: no question about the business after all; a question the information **answers** (the reply gets that information to answer from); or a genuine question it **doesn't answer** (when unsure, this one). (Off-topic messages are spotted by the router, and the assistant politely declines them.) In the last case the flow itself (not the LLM) saves an open `UnansweredQuestion` for that chat, and the assistant is told not to guess and to tell the customer the team will reply in the chat. (The same question isn't saved twice while it's open, and a chat can have at most 5 open questions.) The Chat Sandbox's debug panel shows the check's result. `frontend-app`'s Chats tab shows them in an "Unanswered questions" sub-tab, with an alert while any are open.

All three endpoints need a login and only work on **your own** business (403 without a business, 403 for another business's question, 404 for an unknown one).

- `GET /api/chat/questions/`: your questions, newest first, paginated like chat sessions. Optional: `status` (`open`, `answered`, `dismissed`), `sandbox` (`include` (default), `exclude` or `only`), `ordering` (`created_time`, `answered_time`, `id`; `-` for descending), `page`, `page_size`. Each has the question, `status`, who asked (`chat_session`, `display_name`, `phone_number`, `is_sandbox`), `created_time`, `answered_time`, and `faq` / `answer` once answered.
- `POST /api/chat/questions/{id}/answer/`: `{answer, question?}`. In one go: saves the question (or your rewording) and answer as an FAQ of your business (editable in the FAQ tab; the assistant uses it from then on; an existing FAQ with the same question gets the new answer), sends the answer to the customer in the chat (`business-manual`) as **`Regarding your previous question about "<question>": <answer>`**, and marks the question `answered`. 400 if it isn't open, or the answer is blank or too long.
- `POST /api/chat/questions/{id}/dismiss/`: closes an open question without replying (no FAQ, no message). 400 if it isn't open.

### Orders

When a customer confirms at the Confirmation step (a real or sandbox chat), the [chat flow](#chat-flow) calls `checkout_app.services.place_order()`, which creates an `OrderItem` (`pending_payment`). Products only store a `total_quantity`; their quantities on hold, sold and available are worked out from the orders (`checkout_app/stock.py`), so the new order **puts its quantities on hold**: `quantity_on_hold` goes up and `quantity_available` down. When the order is completed, they move from on hold to sold. The chat goes back to the start with `chat_state_data.last_order_id`, and the reply (sent only after the order is saved) gives the customer the order number.

- **All or nothing, safe under concurrency.** It runs in one transaction with the chat session's row locked. The product rows are locked with `SELECT … FOR UPDATE`, in id order so two orders can't deadlock. Stock is checked again (still on sale, enough left), and once more after the order is saved, with it counted (rolled back if anything is now oversold), so stock can't go negative even on SQLite (which ignores `FOR UPDATE` and locks the whole database instead).
- **If it fails** (e.g. another customer bought the last ones since this customer chose, or the product was deactivated), nothing changes: no order, no stock change, and the chat stays at Confirmation with the problem in the reply ("Only 2 Kopi C are left."), so the customer can change their order.
- The price is the one the customer was shown when choosing (it isn't re-read). Later messages in the same chat don't order again.
- Sandbox chats place orders too, flagged `is_sandbox`, and they count towards stock like real ones.

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
- **Stock is changed through `total_quantity` only.** Raise it to add stock; lower it at most down to on hold + sold, so `quantity_available` never goes negative (otherwise `400`, e.g. `"Must be at least 9 (5 on hold and 4 sold in orders), …"`; Django Admin checks it too). `quantity_available`, `quantity_on_hold` and `quantity_sold` are returned in responses, but sending any of them returns `400 Bad Request`.
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
| `python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions` | Loads the sample data |
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
| `product_app/test_api.py` | Product and FAQ APIs: login required, business scoping and 403s, CRUD, read-only derived quantities, `total_quantity` changes (adding stock, lowering it only down to on hold + sold, re-checked against the latest orders), quantities derived from orders (one orders query per list), validation; list-by-business endpoints (200 / 400 unknown ID / 401 / 403 other business, pagination, read-only); service provider, week and service APIs (CRUD, scoping, the calendar with who booked, adding / closing slots over weeks, copying a week, only O ↔ U editable, booked weeks can't be deleted, free slots) |
| `product_app/tests.py` | Product and FAQ model validation and database constraints (including the description and information limits); sample products and FAQs are valid; migration `0003` moves long descriptions into `information`; `ServiceProvider`, `WeeklyAvailability` (672 letters O / U / H / X, a Monday, one per provider and week) and `Service` (whole 15-minute blocks, many-to-many with providers) models; the migration from the old weekly templates |
| `auth_app/tests.py` | `BusinessUser` model, Django Admin pages load |
| `configuration_app/tests.py` | `BusinessConfiguration` model, random-number endpoint, CORS |
| `chat_app/tests/test_models.py` | `validate_detail_fields`, `validate_chat_messages` and `validate_chat_state_data` rules; `ChatConfiguration` (defaults, `for_business`) and `ChatSession` models (validation, uniqueness, `chat_state_id` must be a step); sample fixtures are valid |
| `chat_app/tests/test_api.py` | Chat endpoint returns the reply, with the LLM mocked (no Ollama needed); chat configuration GET/PUT (401/403, the defaults when none is saved, create vs update, read-only fields, invalid detail fields → 400, the order and booking lists saved independently, left-out fields kept); chat sessions create/list (filters, sorting and pagination on the sample fixtures) and customer messages (LLM mocked); sandbox sessions list/create/delete (only sandbox, only your business) |
| `chat_app/tests/test_questions.py` | Unanswered questions: the model's rules; `ask_business` (saved for the chat, no duplicates, at most 5 open per chat, bad arguments, not a reply tool); `mentioned_products`; the question check in a chat turn (each kind, what the check and the reply are given, invalid output, only when the router finds a question, off topic); the list API (own business only, filters, pagination, 401/403); answering (FAQ created or updated, reworded question, the reply message in the chat, all or nothing, only open questions, permissions) and dismissing; the sample fixture |
| `chat_app/tests/test_tools.py` | The reply step's tools: `get_product_details` (description + information; name in any case, partial name, id, ambiguous names, no description or information, inactive / unknown / another business's products, bad arguments), `list_products` (no information), `list_faqs`, unknown tools; descriptions in the prompt's catalog |
| `chat_app/tests/test_past_orders.py` | The order status branch: whose orders a chat sees (same business and phone number, real or sandbox like the chat; sandbox chats without a number are one customer), the order and booking lists (newest first, statuses, at most 10), numbers asked about (theirs, or "not found" for anyone else's or unknown ones), what the extraction may return, the check that a reply names nothing else, the records text and the fallback reply, and that there are no order tools |
| `chat_app/tests/test_booking_flow.py` | Booking a service (LLM mocked, "now" fixed): a whole booking from start to confirmed, numbered times, exact times (free or taken), parts of the day, closed or past days, a wrong number, changing the service or the time, "change" at confirmation, a time taken before confirming, a question while choosing; the router and when a booking starts; the checks, templates, prompts and state data |
| `chat_app/tests/test_flow.py` | The chat flow (LLM mocked): a whole conversation from start to confirmed, going back on "change", invalid choices, tool calls, invalid JSON → 502; the router (which handlers run for each intent, an order in progress runs whatever the router says, order status questions: extracted, looked up by code among the customer's own orders, rewritten, checked, off topic); custom detail fields (asks for every field, only moves on when all are valid); going back to an earlier step (keeps data, one per message); confirming places an order and reserves stock (once), and a product sold out since it was chosen undoes the confirmation; each step's deterministic check, each detail type's value check and the prompts |
| `checkout_app/tests/test_models.py` | `validate_order_data` rules; `OrderItem` defaults (`pending_payment`), statuses (also the database constraint), total; sample fixture is valid; `validate_schedule_data` rules; `ScheduleItem` times must match its service, same-business links, kept when the service is deleted |
| `checkout_app/tests/test_services.py` | `place_order`: creates the order, which puts its quantities on hold; paid and completed orders count too; all or nothing when any item fails (sold out, inactive, another business's or deleted product); can't oversell; a simulated lost race is stopped by the re-check after saving and rolled back; product rows locked in id order; `place_booking`: books the first free availability, the next one for the same time, keeps the shown price, refuses closed / off-grid / too soon / inactive / other business's, rolls back a clash found after saving |
| `checkout_app/tests/test_stock.py` | Quantities derived from orders: on hold (pending payment, paid) and sold (completed) per product, other businesses' orders ignored, one query; `Product` available / on hold / sold, completing or deleting an order, adding stock, `load_stock` batching and refreshing, `total_quantity` can't go below on hold + sold |
| `checkout_app/tests/test_schedule.py` | Free slots (15-minute grid in local time, open blocks only, bookings and buffers, any active provider, one hour's notice, at most 31 days); bookings marking their blocks (O → H pending, → X paid / completed, back to O when deleted or moved, across weeks, buffers over closed blocks); the week calendar; adding / closing slots over weeks; copying a week |
| `checkout_app/tests/test_api.py` | Orders list/detail: 401, 403 (no business, another business's order), 404 (unknown order, page past the end), 405 (read only), filters, sorting, pagination; bookings list/detail (filters, ordering, scoping, read only) |

### Resetting the local database

To put the data back to the sample state, delete every row (the tables and migrations stay) and reload the fixtures:

```bash
python manage.py flush --noinput
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com
```

> [!WARNING]
> `flush` deletes **all** rows in every table: your own records, the superuser, sessions and blacklisted tokens. Drop `--noinput` to get a confirmation prompt first. Existing JWT tokens stop working, because their users no longer exist until the fixtures are reloaded (and anyone logged in has to log in again).

To delete the database file itself and rebuild it from the migrations (e.g. after migration problems):

```bash
rm db.sqlite3
python manage.py migrate
python manage.py loaddata sample_business_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions
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
| `DJANGO_SCHEDULE_TIME_ZONE` | `Asia/Singapore` | Time zone of the service providers' weekly availability (their 15-minute blocks are local times). |
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
├── chat_app/               # The chat flow (router + order steps), ChatConfiguration (its settings) + temporary one-off chat with the local LLM (Ollama)
│   ├── fixtures/           # sample_chat_configurations.json, sample_chat_sessions.json
│   ├── migrations/
│   ├── admin.py
│   ├── constants.py        # CHAT_STEPS, INTENTS, MESSAGE_SENDERS, DETAIL_FIELD_TYPES, DEFAULT_DETAIL_FIELDS
│   ├── models.py           # ChatConfiguration, ChatSession
│   ├── validators.py       # validate_detail_fields, validate_chat_messages, validate_chat_state_data
│   ├── llm.py              # Ollama client, model, sampling options; structured output + tool-calling helpers
│   ├── flow.py             # The chat flow: router → handlers (order steps, question check) → reply
│   ├── router.py           # The router: what a customer message is about (its intents)
│   ├── order_flow.py       # The order steps: extraction → deterministic checks → state, placing the order
│   ├── prompts.py          # Router prompt, per-step goals, extraction prompts + JSON schemas, question check, reply prompts
│   ├── tools.py            # Read-only tools for the reply step (get_product_details, list_products, list_faqs) + product / FAQ lookups
│   ├── questions.py        # Unanswered questions: ask_business (from the question check), answer_question (→ FAQ + chat reply), dismiss_question
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
│   ├── services.py         # place_order(): creates the order if there's enough stock (locked, all or nothing)
│   ├── stock.py            # Products' quantities on hold / sold, worked out from the orders
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
