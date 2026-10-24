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
python manage.py loaddata sample_business_configurations sample_whatsapp_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions

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
python manage.py loaddata sample_business_configurations sample_whatsapp_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions
```

| Fixture | File | Contents |
| --- | --- | --- |
| `sample_business_configurations` | `configuration_app/fixtures/` | 4 businesses: Kopi & Co. Café (a small business for testing), Bloom & Twine Florist Studio (sells flowers: products only), Lumen & Lens Photography Studio (photo sessions as services, and prints and frames delivered as products), Rally Point Courts (2 badminton and 2 tennis courts, rented by the hour, and a few rackets, shuttlecocks and tennis balls) |
| `sample_business_users` | `auth_app/fixtures/` | 5 business users linked to those businesses |
| `sample_products` | `product_app/fixtures/` | 32 products (one of them inactive). Lumen & Lens Photography Studio has 10 (prints, a canvas, frames, an album, an acrylic block; $18 to $240), made to order from your gallery and delivered anywhere in Singapore. Each has a short description and longer information. Bloom & Twine Florist Studio has 12 realistic products across fresh, dried / preserved, soap and crochet flowers ($5.90 to $288; one sold out, and one down to its last piece), each with detailed information about the product itself (what's in it, size, how long it lasts, care, allergies and pets), with no prices, variants or logistics. Bloom is self-collection only: it doesn't deliver. Kopi & Co. Café's 5 have long, detailed information (ingredients, sizes, options, allergens, storage, and a few product FAQs) for testing `get_product_details`, with some details deliberately left out to test "I don't know". Rally Point Courts has 5 (2 badminton rackets, shuttlecocks, a tennis racket and tennis balls; $9.90 to $329; one sold out, one down to 2), collected at its front counter |
| `sample_services` | `product_app/fixtures/` | Lumen & Lens Photography Studio's 2 photographers (service providers Mei Lin and Arjun) and 8 services (portrait, couple, family, newborn, maternity, graduation, corporate headshots, pets; 30 minutes to 3 hours, $150 to $480), each linked to the photographers who do it; Rally Point Courts's 4 courts (Badminton Court 1 and 2, indoor; Tennis Court 1 and 2, outdoor) and 2 services (Badminton Court (1 hour) $20, Tennis Court (1 hour) $32; starting on the hour). Every provider has availability from 7 Sep 2026: 13 weeks for the photographers (to the week of 30 Nov), 17 for the courts (to the week of 28 Dec), with the bookings already marked: the courts are open 9am to 9pm every day |
| `sample_faqs` | `product_app/fixtures/` | 50 FAQs: 10 for Lumen & Lens Photography Studio (location, payment, changes, delivery of photos, outfits, locations, delivering prints, prints of other photos, damaged prints, collecting prints), 8 for Rally Point Courts (hours, booking length, no equipment rental, but rackets and balls for sale, indoor / outdoor, rain, cancellations, parking and showers, payment), and 12 for Kopi & Co. Café (hours, reservations, halal, delivery, payment, vegetarian options, sugar levels, catering, parking, Wi-Fi, pets, cancellations), 20 for Bloom & Twine Florist Studio (2 of them from answered questions; self-collection only: where and when to collect, same-day collection, collecting for someone else, hours, payment, care, card messages, cancellations, substitutions, corporate, weddings, workshops, allergies and pets…) |
| `sample_chat_configurations` | `chat_app/fixtures/` | 4 configurations: Kopi & Co. Café (orders ask for name, email and pickup time), Bloom & Twine Florist Studio (name, card message and collection date), Lumen & Lens (orders ask for name, email, the photos to print and a delivery address; bookings for name, number of people and optional notes) and Rally Point Courts (orders ask for name and email; bookings for name, email and an optional number of players; with a welcome message and the casual style) |
| `sample_chat_sessions` | `chat_app/fixtures/` | 16 customer chats: 11 with Kopi & Co. Café (at different steps of its flow, over 1–12 Sep, one with no messages yet), 5 with Bloom & Twine Florist Studio (one choosing products, one giving details, and three where customers asked things the FAQs don't cover), 1 with Lumen & Lens (a customer booking a family shoot through the chat). `+6591234567` chats with both the café and the florist. Plus 2 sandbox (test) chats for Kopi & Co. Café, one without a phone number |
| `sample_unanswered_questions` | `chat_app/fixtures/` | 5 questions Bloom & Twine Florist Studio's customers asked that the assistant couldn't answer: 2 answered (now FAQs, with the answer in the chat), 2 open (waiting for the owner) and 1 dismissed |
| `sample_schedule_items` | `checkout_app/fixtures/` | 80 bookings: none in September, some in October and most upcoming in November and December 2026. 12 Lumen & Lens sessions (one from a sandbox chat, one made in the sample chat) and 68 court bookings at Rally Point Courts. Past ones (before 11 Oct 2026) are completed; upcoming ones are paid or pending payment; 5 had their payment fail |
| `sample_order_items` | `checkout_app/fixtures/` | 49 orders: 4 for Kopi & Co. Café (one per status, plus a pending sandbox order), 19 for Lumen & Lens Photography Studio (prints and frames delivered to Singapore addresses, 9 Sep to 11 Oct 2026) and 26 for Bloom & Twine Florist Studio (8 Aug to 12 Sep 2026: birthdays, anniversaries, a Teachers' Day rush, grand openings; mostly completed, the latest paid or pending payment). They aren't linked to chats. They count towards the products' quantities on hold and sold |

Every sample account uses the password **`123`**, so you can log in as anyone while testing:

| Username | Business | Can log in to |
| --- | --- | --- |
| `kopi_owner` | Kopi & Co. Café (1) | API only |
| `bloom_owner` | Bloom & Twine Florist Studio (2) | API only |
| `bloom_staff` | Bloom & Twine Florist Studio (2) | API only |
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
| `checkout_app` | `OrderItem` | `id`, `business` → `BusinessConfiguration`, `chat_session` → `ChatSession` (the chat it was placed in; cleared if the chat is deleted), `is_sandbox`, `order_data` (what was ordered and the customer details, see below), `order_status` (`pending_payment` (default), `payment_received`, `order_completed` or `payment_failed`: a failed payment holds no stock, and a failed booking takes up no time), `payment_reference` (random 128-bit reference, 32 hex characters, generated when the order is made; read only; the payment provider's events come back with it), `created_time`, `updated_time` |
| `checkout_app` | `ScheduleItem` | A booked time slot: `id`, `business`, `chat_session`, `is_sandbox`, `service` and `service_provider` (both kept as null if deleted), `start_time`, `end_time` (start + duration), `blocked_until` (end + buffer), `schedule_data` (`{service: {service_id, name, price, duration_minutes, buffer_minutes}, details: {...}}`), `order_status` and `payment_reference` (like orders), `created_time`, `updated_time` |

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
| `POST` | `/api/auth/signup/` | `{username, email, password, first_name?, last_name?}` → `{access, refresh}` (201) | Sign up: creates an account (Django's password rules; username and email must be free) and logs it in. It has no business yet: create one with `PUT /api/configuration/business/`. |
| `POST` | `/api/auth/firebase/` | `{id_token}` → `{access, refresh, created}` | Log in (or sign up) with **Google or Facebook**: the Identity Platform ID token from the frontend's popup. See below. 401 invalid token or disabled account, 503 not configured. |

**Google / Facebook** (`auth_app/firebase.py`, `auth_app/accounts.py`): frontend-app signs in with the Firebase JS SDK (Google Cloud Identity Platform) and sends the ID token here. It's checked against Google's public keys for our project (`FIREBASE_PROJECT_ID`), then mapped to an account: the one its first login made (`BusinessUser.firebase_uid`), else a new account with no password and no business. It's never attached to an existing account, even with the same email. The response is the same JWT pair as a password login.

- **Access token:** send it as `Authorization: Bearer <access>`. It's valid for **15 minutes**.
- **Refresh token:** valid for **7 days**. It can be used only once, because each refresh returns a new one.
- **Settings:** lifetimes and rotation are configured in `SIMPLE_JWT` in `config/settings.py`.
- **Endpoint access:** the login, sign-up, Google / Facebook, refresh, verify and logout endpoints are public; `me/` needs a login.

### Your business

| Method | URL | What it does |
| --- | --- | --- |
| `GET` | `/api/configuration/business/` | Your business: `id`, `business_name`, `location`, `description`. 404 if your account has none yet. |
| `PUT` | `/api/configuration/business/` | Without a business (a new account), creates it and links your account to it (201). Otherwise updates it (200). |

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
| `GET` | `/api/chat/configuration/` | Your business's chat configuration `{id, business, product_detail_fields, schedule_detail_fields, welcome_message, reply_style, custom_style, last_updated}`; the defaults (with `id` null) if you haven't saved one |
| `GET` | `/api/chat/configuration/reply-styles/` | The reply styles to choose from: `{key, label, description, instructions}` (`instructions` null for `custom`) |
| `GET` / `POST` | `/api/chat/sandbox-sessions/` | List / start your business's sandbox (test) chat sessions |
| `DELETE` | `/api/chat/sandbox-sessions/{id}/` | Delete one of your sandbox chat sessions |
| `GET` | `/api/chat/sessions/` | Your business's chat sessions (real ones by default; `sandbox=include` or `only` for test chats), with filters, sorting and pagination. See [Chat sessions](#chat-sessions) |
| `POST` | `/api/chat/sessions/` | `{phone_number, display_name}` → the new chat session (201). See [Chat sessions](#chat-sessions) |
| `PUT` | `/api/chat/configuration/` | `{product_detail_fields?, schedule_detail_fields?, welcome_message?, reply_style?, custom_style?}`: replace the details your chat asks for (for orders, for bookings), and the welcome message and reply style (validated; left out = kept). Creates the configuration (201) if missing, otherwise 200 |
| `GET` / `POST` | `/api/service-providers/` | List / create your service providers (`GET` / `PUT` / `PATCH` / `DELETE` on `/{id}/`) |
| `GET` | `/api/service-providers/{id}/calendar/?week=YYYY-MM-DD` | A provider's week: its letters and the bookings in it (who booked, their details, status), for the calendar |
| `POST` | `/api/service-providers/{id}/slots/` | `{date_from, date_to, weekdays, time_from, time_to, available}`: open (or close) those days' times, e.g. the next 2 weeks Mon–Fri 09:00–17:00. Booked blocks are left alone |
| `POST` | `/api/service-providers/{id}/copy-week/` | `{source_week, target_week?, weeks?}`: copy a week's open / closed blocks to the next weeks |
| `GET` / `POST` | `/api/weekly-availabilities/` | List (filters `service_provider`, `week_after` / `week_before`) / create your providers' weeks (`GET` / `PUT` / `PATCH` / `DELETE` on `/{id}/`). Only `O` ↔ `U` can be changed; a week with bookings can't be deleted |
| `GET` / `POST` | `/api/services/` | List / create your services (`GET` / `PUT` / `PATCH` / `DELETE` on `/{id}/`); `service_providers` must be your own |
| `GET` | `/api/services/{id}/slots/?date_from=&date_to=` | Every start time the service can be booked at (at most 31 days) |
| `GET` | `/api/schedules/` | Your business's bookings (`ScheduleItem`), latest start first, with filters (`order_status`, `payment_reference`, `sandbox`, `service`, `service_provider`, `start_time_after` / `_before`, `ordering`) and pagination. Read only |
| `GET` | `/api/schedules/{id}/` | One of your bookings (403 another business's, 404 unknown) |
| `POST` | `/api/schedules/{id}/complete/` | Mark a paid booking as completed (payment received → completed; any other status: 400) |
| `GET` | `/api/orders/` | Your business's orders, newest first, with filters, sorting and pagination. Read only. See [Orders](#orders) |
| `GET` | `/api/orders/{id}/` | One of your orders (403 another business's, 404 unknown) |
| `POST` | `/api/orders/{id}/complete/` | Mark a paid order as completed (payment received → completed, its products move from on hold to sold; any other status: 400) |

### WhatsApp connection

Each business can connect one WhatsApp Business number, **with Facebook through WhatsApp Embedded Signup** (`configuration_app/embedded_signup.py`). It goes through **our** Meta app (`META_APP_ID` / `META_APP_SECRET`); businesses don't create their own. The frontend runs Meta's popup and sends what it returns; this service does the rest:

1. swaps the popup's code (valid for 30 seconds) for the business's token, and when it expires (Meta's `expires_in`; unknown if Meta doesn't say);
2. checks the number with that token (`GET /{phone_number_id}`), which also gives the number and name Meta verified;
3. registers the number for Cloud API, with a random two-step verification PIN (saved encrypted: it's needed to register the number again);
4. saves the connection;
5. subscribes our app to the business's WhatsApp Business account (WABA) and overrides its message webhooks to the business's own Callback URL, `MESSAGING_INGESTER_PUBLIC_URL/webhook/<business_id>`, with its verify token. Meta checks that URL straight away (through messaging-ingester and the internal verify-token check), which is why the connection is saved first; if this step fails, it is undone.

`WhatsAppConfiguration` keeps `phone_number_id`, the token, the two-step PIN, the `waba_id`, `verify_token` and Meta's `display_phone_number` / `verified_name`. The token, PIN (and older manual connections' App Secret) are **encrypted at rest** (`configuration_app/crypto.py`, Fernet, key from `CONFIGURATION_ENCRYPTION_KEY`). They, the verify token and the webhook details are **never returned** to the browser. `connection_method` is `embedded_signup`, or `manual` for connections made earlier with a business's own Meta app (the sample data).

**Status from Meta** (`configuration_app/account_updates.py`): Meta reports changes to a business's WhatsApp Business account with `account_update` webhooks to our app's webhook, which messaging-ingester forwards here. They set the connection's `status` and `status_updated_time` (Embedded Signup connections only, found by `waba_id`):

| Meta's event | Status |
| --- | --- |
| `PARTNER_APP_UNINSTALLED` (our app's ID), `PARTNER_REMOVED`, `ACCOUNT_DELETED`, `ACCOUNT_OFFBOARDED` | `disconnected` |
| `DISABLED_UPDATE` with ban state `DISABLE` | `banned` |
| anything else (a scheduled ban, a reinstatement, violations, restrictions, …) | unchanged, logged |

Nothing sets it back automatically: connecting again with Facebook does. The owner's API returns `status`, a `status_reason` to show them (one message per status) and `status_updated_time`.

**Token expiry:** the business's token can expire (e.g. after 60 days, depending on our Facebook Login for Business configuration's token expiration). `access_token_expires_time` keeps when (empty: it doesn't, or isn't known). The API's **`health`** answers "does the owner need to do anything?": `ok`, `expiring_soon` (within 7 days, `ACCESS_TOKEN_EXPIRY_WARNING`, the same as notification-job's first alert), `expired` (replies fail until the owner reconnects), or what Meta reported, `disconnected` / `banned`, which comes first. The frontend warns the owner from it, reconnecting with Facebook gives a new token and expiry, and notification-job alerts the business's users before and at expiry.

**App Secret:** Embedded Signup connections don't store a copy of our App Secret: their signatures and `appsecret_proof` use `META_APP_SECRET` directly (`WhatsAppConfiguration.effective_app_secret`), so rotating it needs no data change. Only older manual connections keep their own app's secret (a database constraint enforces both).

| Method | URL | Auth | What it does |
| --- | --- | --- | --- |
| `GET` | `/api/configuration/whatsapp/` | login | Your business's connection: `phone_number_id`, `display_phone_number`, `verified_name`, `waba_id`, `connection_method`, `status` (`connected` / `disconnected` / `banned`), `status_reason`, `status_updated_time`, `access_token_expires_time`, `health` (`ok` / `expiring_soon` / `expired` / `disconnected` / `banned`), times. 404 if not connected. |
| `POST` | `/api/configuration/whatsapp/embedded-signup/` | login | Connect (201) or replace the connection (200) with `{code, waba_id, phone_number_id}` from the popup. 400 if Meta refused a step (`non_field_errors`, a message for the owner) or the number belongs to another business; 503 if Embedded Signup isn't configured or Meta can't be reached. |
| `DELETE` | `/api/configuration/whatsapp/` | login | Disconnect (204). For Embedded Signup connections, our app is also unsubscribed from the WABA (best effort). |
| `POST` | `/api/internal/whatsapp/<business_id>/verify-token/` | `X-Internal-Api-Key` header | **Service-to-service only** (messaging-ingester). `{verify_token}` → `{valid, phone_number_id}`: does the `hub.verify_token` Meta sent in its webhook handshake match the business's? |
| `POST` | `/api/internal/whatsapp/<business_id>/verify-signature/` | `X-Internal-Api-Key` header | **Service-to-service only** (messaging-ingester). Forward the webhook unchanged: its **raw body** as the request body (`application/octet-stream`) and Meta's `X-Hub-Signature-256` header → `{valid, phone_number_id}`: is the webhook really from Meta? The body is never parsed, since the signature covers the exact bytes. `phone_number_id` (null unless valid) is for matching the payload's `metadata.phone_number_id`. |
| `POST` | `/api/internal/whatsapp/app/verify-token/`, `…/app/verify-signature/` | `X-Internal-Api-Key` header | The same two checks for **our app's own webhook** (`<messaging-ingester>/webhook`), against `META_APP_WEBHOOK_VERIFY_TOKEN` / `META_APP_SECRET`. 404 while they aren't set. |
| `POST` | `/api/internal/whatsapp/app/account-updates/` | `X-Internal-Api-Key` header | **Service-to-service only** (messaging-ingester). Meta's `account_update` events from our app's webhook, `{updates: [{waba_id, event, ban_state?, partner_app_id?}]}` → `{changed}`: sets the status of that WhatsApp Business account's connections (see below). Idempotent. |
| `POST` | `/api/internal/whatsapp/<business_id>/send/` | `X-Internal-Api-Key` header | **Service-to-service only** (messaging-service). Sends a reply from the business's number with the stored token. |

The internal endpoints **never return a secret**: they only answer yes/no, so a leaked `INTERNAL_API_KEY` lets the caller check tokens and signatures but not read them (the user chose this over an endpoint returning the secrets). Wrong or missing key → 403, business not connected → 404, invalid body → 400.

Users without a business (e.g. `superuser`) get 403. The Django admin lists the connections but never shows the secrets, and can't add new ones. Tests never call Meta (every `meta_api` call is patched or uses `httpx.MockTransport`). Meta only runs the popup on HTTPS domains set on our app, so connecting can't be completed locally; the sample data's businesses are already connected (for `mock_whatsapp`).

### Chat configuration

The chat flow is fixed (see [Chat flow](#chat-flow)); the chat configuration holds the settings of its steps, such as the customer details the Details collection and Booking details steps ask for (`product_detail_fields`, `schedule_detail_fields`). Each business has at most one. Both endpoints need a login and work on **your own** business, so there's no ID in the URL. Users without a business (e.g. `superuser`) get 403. `GET` returns the defaults (name and email, with `id` and `last_updated` null) until your business saves its own. `PUT` changes the fields you send (the others are kept); `id`, `business` and `last_updated` are read-only. An invalid list returns 400 with every problem listed under its name (e.g. `product_detail_fields`) (see the rules under [Data model](#data-model)). The sample data gives every sample business a configuration.

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

### Chat flow

The chat flow (the router, the order and booking steps, the question check, the order status lookup and the replies, with the LLM) runs in **`messaging-service`**: its README describes it. It answers the Chat Sandbox's messages (`POST /api/chat/sandbox-sessions/{id}/messages/` there) and customers' WhatsApp messages, placing orders and bookings and saving unanswered questions here, in this service's database. This service has no LLM: it keeps the chat sessions, their settings and the unanswered questions.

### Sandbox chat sessions

Test chats a business starts itself (e.g. from the Chat Sandbox), separate from real customer chats. The endpoints need a login and only work on **your own** business (403 without a business).

- `GET /api/chat/sandbox-sessions/`: your sandbox sessions, paginated, most recent chat first.
- `POST /api/chat/sandbox-sessions/`: `{display_name?, phone_number?}`, both optional. Starts a sandbox session the same way as a real one (`chat_state_id` `start`, no messages, `created_time = last_chat_time = now`). A business can have any number.
- `DELETE /api/chat/sandbox-sessions/{id}/`: deletes the session and its conversation (204). Another business's session → 403; a real customer session → 400 ("Only sandbox chat sessions can be deleted here."); unknown ID → 404.
- Sending a message in a sandbox chat (and getting the reply) is messaging-service's `POST /api/chat/sandbox-sessions/{id}/messages/`: see [Chat flow](#chat-flow).

Sandbox sessions are left out of `GET /api/chat/sessions/` unless you ask for them with `sandbox=include` or `sandbox=only`, and customer messages only ever go to real sessions.

### Unanswered questions

When messaging-service's [chat flow](#chat-flow) finds a question in a customer message, it goes through a **question check**: one extra LLM call (JSON, temperature 0) that sees the business's description, FAQs, products on sale and the full information of any product the message mentions, and decides whether the message is: no question about the business after all; a question the information **answers** (the reply gets that information to answer from); or a genuine question it **doesn't answer** (when unsure, this one). (Off-topic messages are spotted by the router, and the assistant politely declines them.) In the last case the flow itself (not the LLM) saves an open `UnansweredQuestion` for that chat, and the assistant is told not to guess and to tell the customer the team will reply in the chat. (The same question isn't saved twice while it's open, and a chat can have at most 5 open questions.) The Chat Sandbox's debug panel shows the check's result. `frontend-app`'s Chats tab shows them in an "Unanswered questions" sub-tab, with an alert while any are open.

All three endpoints need a login and only work on **your own** business (403 without a business, 403 for another business's question, 404 for an unknown one).

- `GET /api/chat/questions/`: your questions, newest first, paginated like chat sessions. Optional: `status` (`open`, `answered`, `dismissed`), `sandbox` (`include` (default), `exclude` or `only`), `ordering` (`created_time`, `answered_time`, `id`; `-` for descending), `page`, `page_size`. Each has the question, `status`, who asked (`chat_session`, `display_name`, `phone_number`, `is_sandbox`), `created_time`, `answered_time`, and `faq` / `answer` once answered.
- `POST /api/chat/questions/{id}/answer/`: `{answer, question?}`. In one go: saves the question (or your rewording) and answer as an FAQ of your business (editable in the FAQ tab; the assistant uses it from then on; an existing FAQ with the same question gets the new answer), sends the answer to the customer in the chat (`business-manual`) as **`Regarding your previous question about "<question>": <answer>`**, and marks the question `answered`. 400 if it isn't open, or the answer is blank or too long.
- `POST /api/chat/questions/{id}/dismiss/`: closes an open question without replying (no FAQ, no message). 400 if it isn't open.

### Orders

When a customer confirms at the Confirmation step (a real or sandbox chat), messaging-service's [chat flow](#chat-flow) places the order (its `place_order()`), which creates an `OrderItem` (`pending_payment`). Products only store a `total_quantity`; their quantities on hold, sold and available are worked out from the orders (`checkout_app/stock.py`), so the new order **puts its quantities on hold**: `quantity_on_hold` goes up and `quantity_available` down. When the order is completed, they move from on hold to sold. The chat goes back to the start with `chat_state_data.last_order_id`, and the reply (sent only after the order is saved) gives the customer the order number.

- **All or nothing, safe under concurrency.** It runs in one transaction with the chat session's row locked. The product rows are locked with `SELECT … FOR UPDATE`, in id order so two orders can't deadlock. Stock is checked again (still on sale, enough left), and once more after the order is saved, with it counted (rolled back if anything is now oversold), so stock can't go negative even on SQLite (which ignores `FOR UPDATE` and locks the whole database instead).
- **If it fails** (e.g. another customer bought the last ones since this customer chose, or the product was deactivated), nothing changes: no order, no stock change, and the chat stays at Confirmation with the problem in the reply ("Only 2 Kopi C are left."), so the customer can change their order.
- The price is the one the customer was shown when choosing (it isn't re-read). Later messages in the same chat don't order again.
- Sandbox chats place orders too, flagged `is_sandbox`, and they count towards stock like real ones.

`GET /api/orders/` (login required) lists your business's orders, newest first, **including sandbox orders** (they hold real stock). Each has `order_data`, `order_status`, `total` (computed) and the `chat_session` it came from. Optional parameters: `order_status`, `payment_reference`, `sandbox` (`include` (default), `exclude` or `only`), `created_time_after` / `created_time_before`, `ordering` (`created_time`, `order_status` or `id`; `-` for descending), `page` and `page_size` (max 100). The response is paginated like chat sessions. `GET /api/orders/{id}/` returns one order. Orders can't be created, edited or deleted through the API (405), only marked as completed once paid (`POST /api/orders/{id}/complete/`; pending payment → payment received or failed will be set by the payment service).

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
| `python manage.py loaddata sample_business_configurations sample_whatsapp_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions` | Loads the sample data |
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
| `auth_app/test_api.py` | JWT login, refresh + rotation, verify, logout (blacklist), `/api/auth/me/`, CORS for the `Authorization` header; sign up (taken username / email, password rules); Google / Facebook login (new account, same account again, never attached to an existing account with the same email, disabled, invalid token, not configured, rate limits) and the ID token checks (issuer, provider; Google's check is mocked) |
| `product_app/test_api.py` | Product and FAQ APIs: login required, business scoping and 403s, CRUD, read-only derived quantities, `total_quantity` changes (adding stock, lowering it only down to on hold + sold, re-checked against the latest orders), quantities derived from orders (one orders query per list), validation; list-by-business endpoints (200 / 400 unknown ID / 401 / 403 other business, pagination, read-only); service provider, week and service APIs (CRUD, scoping, the calendar with who booked, adding / closing slots over weeks, copying a week, only O ↔ U editable, booked weeks can't be deleted, free slots) |
| `product_app/tests.py` | Product and FAQ model validation and database constraints (including the description and information limits); sample products and FAQs are valid; migration `0003` moves long descriptions into `information`; `ServiceProvider`, `WeeklyAvailability` (672 letters O / U / H / X, a Monday, one per provider and week) and `Service` (whole 15-minute blocks, many-to-many with providers) models; the migration from the old weekly templates |
| `auth_app/tests.py` | `BusinessUser` model, Django Admin pages load |
| `configuration_app/tests.py` | `BusinessConfiguration` model, random-number endpoint, CORS |
| `chat_app/tests/test_models.py` | `validate_detail_fields`, `validate_chat_messages` and `validate_chat_state_data` rules; `ChatConfiguration` (defaults, `for_business`) and `ChatSession` models (validation, uniqueness, `chat_state_id` must be a step); sample fixtures are valid |
| `chat_app/tests/test_api.py` | Chat configuration GET/PUT (401/403, the defaults when none is saved, create vs update, read-only fields, invalid detail fields → 400, the order and booking lists saved independently, left-out fields kept); chat sessions create/list (filters, sorting and pagination on the sample fixtures); sandbox sessions list/create/delete (only sandbox, only your business) |
| `chat_app/tests/test_questions.py` | Unanswered questions: the model's rules; the list API (own business only, filters, pagination, 401/403); answering (FAQ created or updated, reworded question, the reply message in the chat, all or nothing, only open questions, permissions) and dismissing; the sample fixture |
| `checkout_app/tests/test_models.py` | `validate_order_data` rules; `OrderItem` defaults (`pending_payment`), statuses (also the database constraint), total; sample fixture is valid; `validate_schedule_data` rules; `ScheduleItem` times must match its service, same-business links, kept when the service is deleted |
| `checkout_app/tests/test_stock.py` | Quantities derived from orders: on hold (pending payment, paid) and sold (completed) per product, other businesses' orders ignored, one query; `Product` available / on hold / sold, completing or deleting an order, adding stock, `load_stock` batching and refreshing, `total_quantity` can't go below on hold + sold |
| `checkout_app/tests/test_schedule.py` | Free slots (15-minute grid in local time, open blocks only, bookings and buffers, any active provider, one hour's notice, at most 31 days); bookings marking their blocks (O → H pending, → X paid / completed, back to O when deleted or moved, across weeks, buffers over closed blocks); the week calendar; adding / closing slots over weeks; copying a week |
| `checkout_app/tests/test_api.py` | Orders list/detail: 401, 403 (no business, another business's order), 404 (unknown order, page past the end), 405 (read only), filters, sorting, pagination; bookings list/detail (filters, ordering, scoping, read only) |

### Resetting the local database

To put the data back to the sample state, delete every row (the tables and migrations stay) and reload the fixtures:

```bash
python manage.py flush --noinput
python manage.py loaddata sample_business_configurations sample_whatsapp_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput --username superuser --email superuser@example.com
```

> [!WARNING]
> `flush` deletes **all** rows in every table: your own records, the superuser, sessions and blacklisted tokens. Drop `--noinput` to get a confirmation prompt first. Existing JWT tokens stop working, because their users no longer exist until the fixtures are reloaded (and anyone logged in has to log in again).

To delete the database file itself and rebuild it from the migrations (e.g. after migration problems):

```bash
rm db.sqlite3
python manage.py migrate
python manage.py loaddata sample_business_configurations sample_whatsapp_configurations sample_business_users sample_products sample_faqs sample_services sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items sample_unanswered_questions
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
| `CONFIGURATION_ENCRYPTION_KEY` | empty (uses `SECRET_KEY`) | Encrypts the stored WhatsApp secrets (access token, two-step PIN, and older manual connections' App Secret). Any secret string. Changing it (or `SECRET_KEY`, while this is empty) makes the stored secrets unreadable, so businesses must reconnect WhatsApp. |
| `INTERNAL_API_KEY` | `dev-internal-api-key` (only when `DEBUG` is on) | Shared key other services send in the `X-Internal-Api-Key` header to call `/api/internal/`. Empty disables the internal API. |
| `JWT_SIGNING_KEY` | empty (uses `SECRET_KEY`) | Signs the login (JWT) access and refresh tokens. `messaging-service` checks the access tokens with the same key (its Chat Sandbox endpoint), so set it to the same value in both (docker-compose does). Changing it logs everyone out. |
| `MESSAGING_INGESTER_PUBLIC_URL` | `http://localhost:8002` | Public URL of `messaging-ingester`. Embedded Signup points each business's WhatsApp webhooks at `<this>/webhook/<business id>`. |
| `META_GRAPH_API_URL` | `https://graph.facebook.com/v26.0` | Meta's Graph API, used to connect WhatsApp and send replies (`configuration_app/meta_api.py`). Point it at a fake for testing without real Meta credentials. |
| `META_APP_ID` | *(empty)* | Our Meta app's ID, for WhatsApp Embedded Signup ("Connect with Facebook", `POST /api/configuration/whatsapp/embedded-signup/`). Empty: Embedded Signup answers 503. |
| `META_APP_SECRET` | *(empty)* | Our Meta app's App Secret: exchanges Embedded Signup's code, and is saved as those connections' `app_secret` (it signs their webhooks). Empty: Embedded Signup answers 503. |
| `META_APP_WEBHOOK_VERIFY_TOKEN` | *(empty)* | Verify token of our app's own webhook (`<messaging-ingester>/webhook`, set in the App Dashboard). |
| `DJANGO_LOGIN_RATE` / `DJANGO_SIGNUP_RATE` | `30/minute` / `20/hour` | Rate limits per client IP for logging in (password and Google / Facebook) and for signing up (429 when exceeded). |
| `DJANGO_NUM_PROXIES` | `0` | How many proxies append to `X-Forwarded-For`, to find the client's IP for the rate limits. `0` locally; `1` on Cloud Run (Terraform sets it). |
| `FIREBASE_PROJECT_ID` | *(empty)* | The Google Cloud project whose Identity Platform signs the Google / Facebook logins (`POST /api/auth/firebase/`). Empty: that endpoint answers 503; passwords and sign up still work. |
| `DJANGO_DB_ENGINE` | `sqlite` | `sqlite` (`db.sqlite3`, for running without Docker) or `postgresql` (used by `docker-compose.yml`). |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | `configuration_service`, `postgres`, empty, `localhost`, `5432` | The PostgreSQL connection, when `DJANGO_DB_ENGINE=postgresql`. |

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
├── configuration_app/      # Businesses (BusinessConfiguration), WhatsApp connection (WhatsAppConfiguration) + sample API
│   ├── fixtures/           # sample_business_configurations.json
│   ├── migrations/
│   ├── admin.py
│   ├── crypto.py           # Fernet encryption at rest + EncryptedTextField
│   ├── models.py
│   ├── serializers.py      # DRF serializers
│   ├── tests.py            # Endpoint, CORS, model and WhatsApp tests
│   ├── urls.py             # App routes, mounted at /api/configuration/
│   ├── internal_urls.py    # Service-to-service routes, mounted at /api/internal/
│   ├── whatsapp.py         # Webhook checks: verify token + X-Hub-Signature-256 (HMAC-SHA256)
│   └── views.py            # RandomNumberView, WhatsAppConfigurationView, InternalWhatsAppVerifyTokenView, InternalWhatsAppVerifySignatureView
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
├── chat_app/               # Chats: sessions, ChatConfiguration (the chat flow's settings), unanswered questions (the flow itself: messaging-service)
│   ├── fixtures/           # sample_chat_configurations.json, sample_chat_sessions.json
│   ├── migrations/
│   ├── admin.py
│   ├── constants.py        # CHAT_STEPS, MESSAGE_SENDERS, DETAIL_FIELD_TYPES, DEFAULT_DETAIL_FIELDS, the reply styles
│   ├── models.py           # ChatConfiguration, ChatSession
│   ├── validators.py       # validate_detail_fields, validate_chat_messages, validate_chat_state_data
│   ├── questions.py        # Unanswered questions: answer_question (→ FAQ + chat reply), dismiss_question
│   ├── serializers.py      # Chat sessions, ChatConfigurationSerializer, unanswered questions
│   ├── views.py            # Chat sessions, ChatConfigurationView, unanswered questions
│   ├── urls.py             # /api/chat/sessions/, sandbox-sessions/, configuration/, questions/
│   └── tests/
│       ├── test_models.py  # Validator + model tests
│       ├── test_api.py     # Chat sessions + chat configuration API tests
│       └── test_questions.py  # Unanswered questions
├── checkout_app/           # Orders placed when customers confirm in a chat
│   ├── fixtures/           # sample_order_items.json
│   ├── migrations/
│   ├── admin.py
│   ├── models.py           # OrderItem, OrderStatus
│   ├── validators.py       # validate_order_data
│   ├── services.py         # complete_order() / complete_booking() (orders are placed by messaging-service)
│   ├── stock.py            # Products' quantities on hold / sold, worked out from the orders
│   ├── serializers.py      # OrderItemSerializer (read only)
│   ├── filters.py          # OrderItemFilter
│   ├── views.py            # OrderItemListView, OrderItemDetailView
│   ├── urls.py             # /api/orders/, /api/orders/{id}/
│   └── tests/              # test_models.py, test_stock.py, test_schedule.py, test_api.py, test_admin.py
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
