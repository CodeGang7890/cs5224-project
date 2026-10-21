# Xendit Integration

How the project creates Xendit payment links, receives Xendit's result, and updates the order or booking.

## Flow

```
Customer confirms in chat
        │
        ▼
messaging-service saves the order / booking (pending_payment)
        │
        │ POST /payments (X-Internal-Api-Key)
        ▼
payment-ingester creates a Xendit Payment Session (hosted payment link)
        │
        │ {xendit_payment_id, payment_url}
        ▼
messaging-service stores the link on the order / booking and sends it to the customer
        │
        │ customer pays on Xendit's hosted page
        ▼
Xendit sends a webhook to payment-ingester POST /webhook
        │
        │ Pub/Sub: payment-events
        ▼
processing-service checks the amount and updates the order / booking
```

The customer never enters card details on our platform. They pay on Xendit's hosted page.

## payment-ingester

Port: **8001**

### `POST /payments`

Creates a Xendit Payment Session. Called internally by `messaging-service` after an order or booking is saved.

Request:

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

Response:

```json
{
  "xendit_payment_id": "ps_...",
  "payment_url": "https://pay.xendit.co/..."
}
```

`payment_reference` is sent to Xendit as `reference_id`. Xendit echoes it back in its webhooks, which is how the result is matched to the order or booking.

Xendit request created by `payment-ingester`:

- `POST https://api.xendit.co/sessions`
- `Authorization: Basic base64("<XENDIT_SECRET_KEY>:")`
- `session_type: PAY`
- `mode: PAYMENT_LINK`
- `reference_id`: our `payment_reference`
- `amount`, `currency`, `country`
- customer email (maximum 50 characters)
- customer name sanitized to Xendit's `individual_detail`
- `allowed_payment_channels` (default: `CARDS`)
- `success_return_url` / `cancel_return_url` only when they are HTTPS

### `POST /webhook`

Receives Xendit webhooks.

- Authentication: static `x-callback-token` header, compared with `XENDIT_WEBHOOK_SECRET`.
- This is **not** an HMAC signature. Xendit sends the configured webhook token itself.
- An empty `XENDIT_WEBHOOK_SECRET` rejects every webhook.

Events acted on:

| Xendit event | Result |
| --- | --- |
| `payment_session.completed` | `success` |
| `payment.capture` | `success` |
| `payment.succeeded` | `success` |
| `payment_session.expired` | `fail` |
| `payment.failure` | `fail` |

Other events are ignored with HTTP 200.

Pub/Sub message published to `payment-events`:

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

Attributes:

- `payment_reference`
- `status`

## processing-service

Port: **8003**

Pulls `payment-events` and applies each event in `processing-service/app/payments.py`:

1. Finds the order or booking by `payment_reference`.
2. Checks the amount against the stored order / booking total.
   - A successful payment **must** carry the exact total.
   - A failed payment may omit its amount, but if present it must also match.
   - A mismatch is logged and acked (redelivering it would not help).
3. Updates the status:
   - `success` → `payment_received`
   - `fail` → `payment_failed`
4. A failed payment is final. There is no automatic retry and no customer "try again" action.
5. For received payments, it renders and uploads the invoice, then tells the customer on WhatsApp.

## Frontend

- Business payment dashboard: `/orders/payment`
  - Shows product orders and service bookings.
  - Shows payment status, payment reference, Xendit payment ID, total, and the Xendit payment link when one exists.
  - Read only. It does not create or resend payment links.
- Public customer result pages:
  - `/payment/success`
  - `/payment/failed`

These public pages are only used when `XENDIT_SUCCESS_URL` and `XENDIT_FAILURE_URL` are set to HTTPS URLs. Locally, leave them empty so Xendit uses its own hosted result page.

## Local setup

Copy the root env example:

```powershell
Copy-Item .env.example .env
```

Fill in the Xendit values in `.env`:

```env
XENDIT_SECRET_KEY=
XENDIT_WEBHOOK_SECRET=dev-xendit-webhook-secret
XENDIT_API_BASE_URL=https://api.xendit.co
XENDIT_COUNTRY=SG
XENDIT_CURRENCY=SGD
XENDIT_ALLOWED_PAYMENT_CHANNELS=CARDS
XENDIT_SESSION_EXPIRY_SECONDS=1800
XENDIT_SUCCESS_URL=
XENDIT_FAILURE_URL=
```

Then start the stack:

```powershell
docker compose up --build
```

For Xendit webhooks to reach the local service, expose `http://localhost:8001` with a public HTTPS tunnel (for example ngrok) and use that URL in the Xendit dashboard.

## Xendit dashboard

### API key

- Use a **test mode** secret key for local development.
- Store it in `XENDIT_SECRET_KEY`.
- It is server-side only. Never put it in the frontend.

### Webhook

- Callback URL: `https://your-public-url/webhook`
- Webhook token: must match `XENDIT_WEBHOOK_SECRET`
- Events:
  - `payment_session.completed`
  - `payment_session.expired`
  - optionally `payment.failure`
  - optionally `payment.capture`
  - optionally `payment.succeeded`

### Return URLs

If set, they must be HTTPS:

- Success: `https://your-frontend/payment/success`
- Failure / cancel: `https://your-frontend/payment/failed`

If empty, Xendit's hosted result page is used.

## Failure paths

| Failure | Behaviour |
| --- | --- |
| No customer name or email | No payment link is created. The chat sends a note instead. The order / booking stays `pending_payment`. |
| `payment-ingester` is unreachable | The chat flow degrades gracefully: the order / booking is saved, but the customer gets a note instead of a link. |
| Xendit refuses session creation | The order / booking stays `pending_payment`. The customer gets a note. |
| Webhook token invalid | `payment-ingester` returns 401. Nothing is published. |
| Webhook amount mismatches the order / booking total | `processing-service` rejects the event, logs it, and acks it. The status is not changed. |
| Payment expires or fails | The order / booking becomes `payment_failed`. A failed booking frees its time slot. A failed order frees its held stock. No retry is offered. |
| Duplicate webhook / Pub/Sub redelivery | Applying the same event again changes nothing. |

## Testing the webhook locally

Example success event:

```bash
curl -i http://localhost:8001/webhook \
  -H "Content-Type: application/json" \
  -H "x-callback-token: dev-xendit-webhook-secret" \
  -d '{
    "event": "payment_session.completed",
    "id": "evt_test",
    "data": {
      "reference_id": "3f9c1a2b4d5e6f708192a3b4c5d6e7f8",
      "status": "COMPLETED",
      "amount": 3.6,
      "currency": "SGD",
      "payment_session_id": "ps_test"
    }
  }'
```

The amount must match the order / booking total, or `processing-service` will reject it.

Example failure event:

```bash
curl -i http://localhost:8001/webhook \
  -H "Content-Type: application/json" \
  -H "x-callback-token: dev-xendit-webhook-secret" \
  -d '{
    "event": "payment_session.expired",
    "id": "evt_test",
    "data": {
      "reference_id": "3f9c1a2b4d5e6f708192a3b4c5d6e7f8",
      "status": "EXPIRED",
      "amount": 3.6,
      "currency": "SGD",
      "payment_session_id": "ps_test"
    }
  }'
```

## Security notes

- `XENDIT_SECRET_KEY` creates payments and must stay server-side.
- `XENDIT_WEBHOOK_SECRET` is a static shared token. Keep it random and do not commit real values.
- Webhooks must arrive over HTTPS in production.
- Do not commit `.env`. Use `.env.example` for placeholders.

## GCP Secret Manager (later)

When replacing local env files with GCP Secret Manager:

```bash
gcloud secrets create xendit-secret-key --replication-policy=automatic
gcloud secrets versions add xendit-secret-key --data-file <(echo "your-xendit-secret-key")

gcloud secrets create xendit-webhook-token --replication-policy=automatic
gcloud secrets versions add xendit-webhook-token --data-file <(echo "your-xendit-webhook-token")
```

For Cloud Run:

```bash
gcloud run services deploy payment-ingester \
  --set-secrets XENDIT_SECRET_KEY=xendit-secret-key:latest \
  --set-secrets XENDIT_WEBHOOK_SECRET=xendit-webhook-token:latest
```

The team's Terraform in `infrastructure/` already anticipates `payment-ingester`; wire the secrets there when deploying.
