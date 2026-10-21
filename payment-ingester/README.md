# payment-ingester

Creates **Xendit Payment Sessions** for placed orders / bookings and receives **Xendit payment webhooks**. It publishes payment events to **Pub/Sub** (topic `payment-events`) for `processing-service`. Runs on port **8001**.

## Architecture

```
messaging-service ──POST /payments──▶ payment-ingester ──POST /sessions──▶ Xendit
                                                                    │
customer pays on Xendit's hosted page                               │
                                                                    ▼
processing-service ◀──Pub/Sub── payment-ingester ◀──POST /webhook── Xendit
```

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Health check |
| `POST /payments` | Internal endpoint used by `messaging-service` to create a Xendit Payment Session |
| `POST /webhook` | Xendit webhook receiver |

## `POST /payments`

Creates the hosted payment link the customer pays on.

- Auth: `X-Internal-Api-Key` header (must equal `INTERNAL_API_KEY`)
- Request body:

```json
{
  "kind": "order",
  "item_id": 12,
  "amount": 3.6,
  "payment_reference": "3f9c1a2b4d5e6f708192a3b4c5d6e7f8",
  "customer": {
    "given_name": "Alice Tan",
    "email": "alice@example.com"
  },
  "description": "Order #12"
}
```

- Response `201`:

```json
{
  "xendit_payment_id": "ps_...",
  "payment_url": "https://pay.xendit.co/..."
}
```

## `POST /webhook`

- Auth: `x-callback-token` header, compared with `XENDIT_WEBHOOK_SECRET`
- Events acted on:
  - `payment_session.completed` → `success`
  - `payment.capture` → `success`
  - `payment.succeeded` → `success`
  - `payment_session.expired` → `fail`
  - `payment.failure` → `fail`
- Other events are ignored with `200`
- Publish failure returns `503`, so Xendit retries

Pub/Sub message data:

```json
{
  "payment_reference": "3f9c1a2b4d5e6f708192a3b4c5d6e7f8",
  "status": "success",
  "xendit_payment_id": "ps_...",
  "amount": 3.6,
  "currency": "SGD",
  "event_id": "evt_..."
}
```

Attributes: `payment_reference`, `status`.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `PORT` | `8001` | Server port |
| `WEB_CONCURRENCY` | `2` | Gunicorn workers |
| `XENDIT_SECRET_KEY` | *required for `POST /payments`* | Xendit secret key (server-side only) |
| `XENDIT_API_BASE_URL` | `https://api.xendit.co` | Xendit API base URL |
| `XENDIT_COUNTRY` | `SG` | Customer country |
| `XENDIT_CURRENCY` | `SGD` | Payment currency |
| `XENDIT_ALLOWED_PAYMENT_CHANNELS` | `CARDS` | Comma-separated allowed channels |
| `XENDIT_SESSION_EXPIRY_SECONDS` | `1800` | Payment link expiry |
| `XENDIT_TIMEOUT_SECONDS` | `15` | Xendit API timeout |
| `XENDIT_SUCCESS_URL` | empty | Must be HTTPS if set |
| `XENDIT_FAILURE_URL` | empty | Must be HTTPS if set |
| `XENDIT_WEBHOOK_SECRET` | *required for webhooks* | Static `x-callback-token` value |
| `INTERNAL_API_KEY` | `dev-internal-api-key` | Shared key for `POST /payments` |
| `GCP_PROJECT_ID` | `local-project` | GCP project ID |
| `PUBSUB_TOPIC` | `payment-events` | Pub/Sub topic |
| `PUBSUB_PUBLISH_TIMEOUT_SECONDS` | `5` | Publish timeout |
| `PUBSUB_EMULATOR_HOST` | unset | Local Pub/Sub emulator host:port |

## Testing

```bash
cd payment-ingester
python -m unittest -v
```

## Running

### With Docker

From the repository root:

```bash
docker compose up --build payment-ingester
```

### Without Docker

```bash
cd payment-ingester
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

## Project structure

```
payment-ingester/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── routes.py
│   ├── schemas.py
│   ├── xendit_api.py
│   ├── xendit_webhook.py
│   └── publisher.py
├── scripts/
│   └── publish_dummy_payments.py
├── Dockerfile
├── gunicorn.conf.py
├── run.py
├── requirements.txt
└── README.md
```

## Security notes

- Never commit `XENDIT_SECRET_KEY` or a real `XENDIT_WEBHOOK_SECRET`.
- Use HTTPS in production.
- Keep the Xendit secret key server-side only.
