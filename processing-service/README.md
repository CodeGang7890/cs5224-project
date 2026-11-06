# processing-service

A **FastAPI** service, served by **Gunicorn**, on port **8003**. It pulls the **payment events** payment-ingester publishes to Pub/Sub (topic `payment-events`). For each, it updates the order or booking with that payment reference in configuration-service's PostgreSQL (SQLAlchemy). For a paid order or booking it also makes an **invoice PDF**, uploads it to Cloud Storage, and tells the customer on **WhatsApp**.

| Port | Service |
| --- | --- |
| 8000 | configuration-service |
| 8001 | payment-ingester |
| 8002 | messaging-ingester |
| **8003** | **processing-service** |
| 8004 | messaging-service |

## API

| Method | Path | |
| --- | --- | --- |
| `GET` | `/` | Hello world / health check: `{"message": "Hello, world! processing-service is running"}` |

Swagger UI is at <http://localhost:8003/docs>, and the OpenAPI spec at `/openapi.json`.

## Pub/Sub consumer

`app/consumer.py` is a **pull** subscriber (streaming pull) on its own subscription, `processing-service-payments`, to the topic `payment-events`. Each message's data is JSON `{payment_reference, status, amount?}` (32 hex characters; `success` / `fail`; the amount Xendit reports; see `payment-ingester/README.md`).

`payment-ingester` converts the Xendit webhook into this flat event before publishing it. The consumer also accepts nested Xendit `data` payloads with `reference_id`, `status`, and `amount`: `COMPLETED` / `SUCCEEDED` map to `success`, and `EXPIRED` / `FAILED` / `CANCELED` map to `fail`. Unknown or missing statuses are rejected rather than treated as failed payments. In GCP, Terraform configures the topic as `payment-queue` and the subscription as `payment-queue-worker`.

**Two kinds of event** share the topic. `success` / `fail` are a payment's **result** (Xendit's webhook): the payment flow below updates the order / booking and the customer gets a **receipt** (or a failure notice). `created` is published by payment-ingester when an order / booking is placed and its payment link is made, with that link as `payment_url` (`{payment_reference, status: "created", amount, payment_url, …}`): the customer gets an **invoice**, and nothing in the database changes (`send_invoice` in `app/payments.py`). An invoice is only made for an order / booking still pending payment: a late `created` event for one that is already paid or failed is logged and acked, so nobody gets an invoice after paying.

- **Valid:** it goes through the payment flow (below), then is acked. A repeated event changes nothing in the database (but see step 5).
- **Unknown payment reference, amount mismatch, or not pending payment** (e.g. already completed): logged as an error and acked.
- **Processing raised** (e.g. the database, Cloud Storage or configuration-service is down): nacked, so Pub/Sub redelivers it. The payment itself is already committed by then; the retry sees a repeated event and finishes the receipt and the message.
- **Malformed:** logged as a warning and acked, so it isn't redelivered forever.

It starts and stops with the app. Each Gunicorn worker runs one, and they share the messages. It's off unless `PUBSUB_CONSUMER_ENABLED` is set; docker-compose turns it on. With the emulator (`PUBSUB_EMULATOR_HOST`), the consumer creates its subscription itself.

To try it end to end, publish dummy events with payment-ingester's script, then watch `docker compose logs -f processing-service`.

## Payment flow (`app/payments.py`)

In one transaction, with the row locked:

1. Find the product order (`checkout_app_orderitem`) or booking (`checkout_app_scheduleitem`) with the payment reference. None: `PaymentNotFoundError`.
2. Check the amount against the order / booking total. A successful payment must carry the exact total; a failed payment's amount, when present, must also match. A mismatch: `PaymentEventError`.
3. Only `pending_payment` changes: `success` → `payment_received`, `fail` → `payment_failed`. Already in that status: nothing changes. Any other status: `PaymentStatusConflictError`. A failed payment is final (no retry).
4. **Product orders:** nothing else is stored. configuration-service works out each product's on hold / sold / available quantities from the orders' statuses: payment received still holds them, and a failed payment holds nothing, so they're available again.
5. **Bookings:** the provider's weekly availability letters are stored, and Django's signals don't run here, so `app/schedule.py` (a port of configuration-service's `checkout_app.schedule`) paints them. Paid: on hold (H) → booked (X) over the duration, and the buffer where open. Failed: back to available (O).

Then, **after the commit** (so a failure here never undoes the payment, and no connection is held during the upload):

6. **Receipt (payment received only).** `app/documents.py` builds the receipt (`build_document(…, RECEIPT)`, numbered `RCT-O-000012` / `RCT-B-000028`) from the order / booking, its business, chat and provider, then draws the PDF (`render_pdf`, fpdf2). `app/storage.py` uploads it to `receipts/<payment_reference>.pdf` in the `GCS_BUCKET` bucket, so a repeated event just overwrites it, and makes a signed link valid for 7 days. Without `GCS_BUCKET` (local development, the tests) the PDF is made but not uploaded, and there is no link.
7. **Tell the customer.** `app/notifications.py` tries two channels, and one failing doesn't stop the other. **WhatsApp** (received and failed): it sends a message to the chat's phone number, with the receipt link when there is one. It goes through `app/whatsapp_sender.py`: configuration-service's `POST /api/internal/whatsapp/<business_id>/send/`, which holds the business's access token (the same call messaging-service makes). A chat without a phone number (a Chat Sandbox, or a deleted chat) isn't messaged. **Email** (received only): the receipt PDF is attached to an email sent to the `email` detail the customer gave in the chat (see below).

Things to know about the message:

- **A repeated event sends them again.** Nothing stored says it was sent (the schema is configuration-service's), and a customer who gets a message twice is better off than one who never gets it.
- **Temporary failure** (configuration-service, Meta or the mail relay can't be reached): raises once both channels have been tried, so the event is redelivered. **A refusal** (Meta says no, or the business hasn't connected WhatsApp): logged as an error, and the payment still stands.
- **The 24-hour window:** free-form WhatsApp text only works within 24 hours of the customer's last message. A customer who pays later than that gets a Meta refusal (logged). Reaching them then needs an approved message template, which isn't built.
- **Signed links need a service account.** Your own `gcloud auth application-default login` can't sign, so locally the invoice is uploaded but the message has no link. On Cloud Run the runtime service account needs `roles/iam.serviceAccountTokenCreator` on itself.

`app/models.py` maps only the columns the flow needs. configuration-service (Django) owns the schema and every migration: this service never creates or alters tables.

| Variable | Default | |
| --- | --- | --- |
| `PUBSUB_CONSUMER_ENABLED` | off | `true` / `1` / `yes` turns the consumer on |
| `GCP_PROJECT_ID` | `local-project` | |
| `PUBSUB_TOPIC` / `PUBSUB_SUBSCRIPTION` | `payment-events` / `processing-service-payments` | |
| `PUBSUB_MAX_MESSAGES` | `5` | Messages handled at once, per worker |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `configuration_service` / `postgres` / `postgres` | configuration-service's database |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5433` | docker-compose: `postgres` / `5432` |
| `DATABASE_URL` | unset | A full SQLAlchemy URL; overrides the above |
| `SCHEDULE_TIME_ZONE` | `Asia/Singapore` | Must equal configuration-service's `DJANGO_SCHEDULE_TIME_ZONE` |
| `GCS_BUCKET` | unset | The bucket for the invoice and receipt PDFs (`cs5224-ansera-app-objects`). Unset: they aren't uploaded |
| `EMAIL_ENABLED` | off | `true` turns email on. Off, `send_email()` only logs what it would send |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | unset / `Ansera` | The sender, which the provider must have verified |
| `SMTP_HOST` / `SMTP_PORT` | `smtp-relay.brevo.com` / `587` | Connects, then upgrades to TLS (STARTTLS), which is what port 587 expects. Cloud Run blocks port 25 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | unset | The provider's SMTP login and key (not the account password). In production the key goes in Secret Manager |
| `INVOICE_CURRENCY` | `SGD` | Shown on the invoice, the receipt and in the messages |
| `CONFIGURATION_SERVICE_URL` | `http://localhost:8000/api` | docker-compose: `http://configuration-service:8000/api` |
| `INTERNAL_API_KEY` | `dev-internal-api-key` | Must equal configuration-service's |
| `PUBSUB_EMULATOR_HOST` | unset | `host:port` of the local emulator (docker-compose: `pubsub-emulator:8085`) |

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
python run.py                                      # http://127.0.0.1:8003 (consumer off)
gunicorn -c gunicorn.conf.py "app:create_app()"   # or as in Docker
```

## Tests

```bash
python -m unittest -v
```

`tests/test_schema.py` (2 tests) is skipped unless `SCHEMA_DATABASE_URL` points at a database migrated by configuration-service; CI's `schema` job runs it.

## The invoice and the receipt (`app/documents.py`, `app/notifications.py`)

The customer gets two different PDFs, by WhatsApp and by email:

| | **Invoice** | **Receipt** |
| --- | --- | --- |
| When | The order / booking is placed (a `created` event) | The payment is received (`success`) |
| PDF | Title **INVOICE**, `INV-O-000012` (booking: `INV-B-000028`), "Issued <date>", **Amount due**, **HOW TO PAY** with the payment link, "This is an invoice, not a receipt" | Title **RECEIPT**, `RCT-O-000012`, "Paid <date>", **Total paid**, "Thank you for your order" |
| Stored at | `invoices/<payment_reference>.pdf` | `receipts/<payment_reference>.pdf` |

## Email

`send_email(subject, content, recipient, attachments=[...])` sends through an SMTP relay (Brevo) with Python's built-in `smtplib`.

- **Off by default.** Without `EMAIL_ENABLED=true` it returns `False` and only logs, so development and the tests never email anyone. docker-compose reads the settings from the root `.env`.
- **A failure says whether to retry** (`EmailError.retryable`): the relay couldn't be reached, or answered with a temporary error (yes), or the login or address was refused, or the settings are incomplete (no). A caller handling a Pub/Sub event can raise only the first kind, so the event is redelivered.

**The receipt email.** After a payment is received, the customer gets "Payment received: your order with <business>" from `EMAIL_FROM_NAME`, with `RCT-O-000012.pdf` attached (the invoice email, when the order is placed, has `INV-O-000012.pdf`). The PDF is attached rather than linked, so it works without Cloud Storage, locally and in production, and never expires. The address comes from the order's `email` detail (`Document.customer_email`); one that doesn't look like an address is ignored. Failed payments aren't emailed.

To try sending an email:

```bash
python scripts/send_test_email.py name@mail.com
```

`check_storage.py` deletes its file again unless you pass `--keep`.

## Project structure

```
processing-service/
├── app/
│   ├── __init__.py   # create_app()
│   ├── config.py     # PORT = 8003, WORKERS, API title
│   ├── routes.py     # GET /
│   ├── consumer.py   # Pub/Sub pull consumer of the payment events
│   ├── payments.py   # the payment flow
│   ├── documents.py  # the invoice and the receipt: their data from the rows, and the PDFs (fpdf2)
│   ├── storage.py    # the PDFs in Cloud Storage, and their signed links
│   ├── notifications.py   # what the customer is told: the invoice, the receipt, a failed payment
│   ├── email_sender.py    # send_email() through an SMTP relay (Brevo)
│   ├── whatsapp_sender.py # configuration-service's internal send endpoint
│   ├── schedule.py   # painting a booking into its provider's weeks
│   ├── models.py     # SQLAlchemy models of configuration-service's tables
│   ├── db.py         # engine and sessions (lazy)
│   ├── schemas.py
│   └── errors.py     # JSON error bodies (as in messaging-ingester)
├── scripts/          # preview_documents.py (PDFs to look at), check_storage.py (a real upload), send_test_email.py (a real email)
├── tests/          # test_routes.py, test_consumer.py (fake Pub/Sub clients), test_payments.py (SQLite, fake storage and sender),
│                   # test_documents.py, test_storage.py, test_notifications.py, test_whatsapp_sender.py, test_schema.py
├── gunicorn.conf.py
├── run.py            # development server
└── Dockerfile
```
