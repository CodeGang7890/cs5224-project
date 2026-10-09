# Messaging Ingester

FastAPI service on **port 8002** that receives Meta's **WhatsApp webhooks**, checks they really come from Meta, and publishes each customer message to **Pub/Sub** for `messaging-service` to handle.

```
Customer ─► Meta ─► POST /webhook/<business_id> ─► configuration-service: "is this signature valid?"
                         │                             (yes/no, the secrets never leave it)
                         └─► Pub/Sub topic "whatsapp-inbound-messages" ─► messaging-service
```

It holds **no secrets and no database**. Each business's WhatsApp settings (Phone Number ID, App Secret, access token, verify token) live in `configuration-service`. For every webhook, the ingester asks its internal API to check the verify token or the signature, and gets a yes/no answer.

## Endpoints

| Method | URL                      | What it does                                                                  |
| ------ | ------------------------ | ----------------------------------------------------------------------------- |
| `GET`  | `/`                      | Health check                                                                  |
| `GET`  | `/webhook/{business_id}` | Meta's verification handshake (when the owner saves the Callback URL in Meta) |
| `POST` | `/webhook/{business_id}` | Incoming WhatsApp events                                                      |
| `GET`  | `/docs`                  | Swagger UI                                                                    |

Each business has its own Callback URL, `<public URL>/webhook/<business_id>`. The frontend shows it, together with the verify token, under Home → WhatsApp (`configuration-service`'s `GET /api/configuration/whatsapp/`).

### `GET /webhook/{business_id}`: verification handshake

Meta calls it once with `hub.mode=subscribe`, `hub.verify_token` and `hub.challenge`.

| Status | When                                                                                                |
| ------ | --------------------------------------------------------------------------------------------------- |
| `200`  | The token is the business's: the body is `hub.challenge` (plain text), which completes Meta's check |
| `403`  | Wrong `hub.verify_token`, or `hub.mode` isn't `subscribe`                                           |
| `404`  | The business hasn't connected WhatsApp                                                              |
| `422`  | A `hub.*` parameter is missing                                                                      |
| `503`  | configuration-service is unreachable                                                                |

### `POST /webhook/{business_id}`: incoming events

1. The raw body and Meta's `X-Hub-Signature-256` header are forwarded **unchanged** to configuration-service, which checks the HMAC-SHA256 with the business's App Secret. The body is never re-serialized, because the signature covers the exact bytes.
2. The JSON is parsed. Only changes for the business's own Phone Number ID are used (others are logged and skipped). Delivery/read receipts (`statuses`) are ignored.
3. Each customer message is published to Pub/Sub, and the ingester waits until Pub/Sub has accepted them.

| Status | When                                               |
| ------ | -------------------------------------------------- |
| `200`  | `{"published": <n>}`: done (`0` for receipts only) |
| `400`  | Correctly signed, but the body isn't JSON          |
| `401`  | Missing or wrong signature: nothing is published   |
| `404`  | The business hasn't connected WhatsApp             |
| `503`  | configuration-service or Pub/Sub is unavailable    |

Meta retries any non-200 answer, so a `503` loses nothing.

## Pub/Sub message contract (for messaging-service)

Topic: **`whatsapp-inbound-messages`**. One Pub/Sub message per customer message.

**Data** (UTF-8 JSON):

```json
{
  "business_id": 1,
  "phone_number_id": "1359207187280395",
  "message_id": "wamid.HBgKNjU5MTIzNDU2NxUCABIYIEE1NUY2...",
  "from": "+6591234567",
  "display_name": "Alice",
  "type": "text",
  "text": "Hi! Do you have pandan chiffon cake?",
  "timestamp": "2026-10-07T09:45:59+00:00"
}
```

| Field             | Notes                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------- |
| `business_id`     | From the Callback URL; the signature check proves the webhook is for this business           |
| `phone_number_id` | The business's WhatsApp Phone Number ID (send replies to `POST /{phone_number_id}/messages`) |
| `message_id`      | Meta's unique `wamid…` ID                                                                    |
| `from`            | The customer, E.164 with `+` (the same format as `ChatSession.phone_number`)                 |
| `display_name`    | The customer's WhatsApp profile name, or `null`                                              |
| `type`            | `text`, `image`, `audio`, `location`, ...                                                    |
| `text`            | The text for `text` messages; `null` for every other type                                    |
| `timestamp`       | When the customer sent it, ISO 8601 UTC                                                      |

**Attributes:** `business_id`, `phone_number_id`, `message_id` (strings).
**Ordering key:** the customer's number (`from`), so one customer's messages arrive in order when the subscription has message ordering enabled.

**What the consumer must handle:**

- **Duplicates:** Meta can redeliver a webhook, and a webhook whose publish partly failed is retried as a whole. Drop messages whose `message_id` was already processed.
- **New customers:** create the `ChatSession` when the number is new (`CustomerMessageView` currently answers 404 instead).
- **Replying:** messaging-service will need the business's access token, which stays in configuration-service. The plan is a "send this message" endpoint there, rather than handing out the token.

## Configuration

Environment variables (constants are in `app/config.py`):

| Variable                    | Default                     | Description                                                                                                                                                                                          |
| --------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CONFIGURATION_SERVICE_URL` | `http://localhost:8000/api` | configuration-service API root                                                                                                                                                                       |
| `INTERNAL_API_KEY`          | `dev-internal-api-key`      | Must equal configuration-service's `INTERNAL_API_KEY` (`X-Internal-Api-Key` header)                                                                                                                  |
| `GCP_PROJECT_ID`            | `local-project`             | Google Cloud project of the Pub/Sub topic                                                                                                                                                            |
| `PUBSUB_TOPIC`              | `whatsapp-inbound-messages` | Topic to publish to                                                                                                                                                                                  |
| `PUBSUB_EMULATOR_HOST`      | unset                       | `host:port` of the local Pub/Sub emulator. When set, the client library uses it instead of Google Cloud, and the ingester creates the topic and the `whatsapp-inbound-debug` subscription at startup |
| `PORT`                      | `8002`                      | Port (Cloud Run sets it)                                                                                                                                                                             |

On Google Cloud, the topic and the messaging-service subscription come from Terraform (not done yet), and the service account needs `roles/pubsub.publisher` on the topic.

## Running

### With Docker (recommended)

From the repository root, `docker compose up --build` starts the ingester with configuration-service and a local **Pub/Sub emulator** (in memory, emptied on restart).

To see what was published, pull the debug subscription (each message is shown once):

```bash
docker compose exec messaging-ingester python scripts/pull_debug.py
```

### Trying it without Meta

Connect WhatsApp for a business first (frontend Home → WhatsApp, or `PUT /api/configuration/whatsapp/`), then act as Meta. With App Secret `my-app-secret` and Phone Number ID `123456789`:

```bash
# Handshake: prints the challenge if the verify token is right
curl "http://localhost:8002/webhook/1?hub.mode=subscribe&hub.verify_token=<verify token>&hub.challenge=12345"

# A signed message
BODY='{"object":"whatsapp_business_account","entry":[{"id":"1","changes":[{"field":"messages","value":{"metadata":{"phone_number_id":"123456789"},"contacts":[{"wa_id":"6591234567","profile":{"name":"Alice"}}],"messages":[{"from":"6591234567","id":"wamid.TEST1","timestamp":"1760000000","type":"text","text":{"body":"Hi!"}}]}}]}]}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac my-app-secret | awk '{print $2}')"
printf '%s' "$BODY" | curl -X POST -H 'Content-Type: application/json' -H "X-Hub-Signature-256: $SIG" --data-binary @- http://localhost:8002/webhook/1
```

### With real WhatsApp messages

Meta needs a public HTTPS URL. Expose the local ingester with a tunnel, e.g. `cloudflared tunnel --url http://localhost:8002`. In Meta (WhatsApp → Configuration → Webhook), enter `https://<tunnel host>/webhook/<business_id>` as the Callback URL and the verify token from the frontend, then subscribe to the `messages` field. Messages sent to the business's number then show up in `pull_debug.py`.

### Without Docker

Python 3.10+ is needed. Run this from `messaging-ingester/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                      # http://127.0.0.1:8002, Swagger UI at /docs
```

Without `PUBSUB_EMULATOR_HOST`, publishing uses real Google Cloud credentials.

## Running tests

```bash
python -m unittest -v                                   # from messaging-ingester/
# or, from the repository root, inside the Docker image:
docker compose run --rm --no-deps -v "$PWD/messaging-ingester:/app" messaging-ingester python -m unittest -v
```

configuration-service and Pub/Sub are replaced by fakes (`tests/helpers.py`, FastAPI `dependency_overrides`, `httpx.MockTransport`, a mocked Pub/Sub client). `EmulatorIntegrationTests` publishes through the real client library and pulls the result back. It runs only when `PUBSUB_EMULATOR_HOST` is set, which is the case inside docker compose (start the emulator with `docker compose up -d pubsub-emulator`).

| File                    | Covers                                                                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_webhook.py`       | Handshake and incoming events: every status code, exact bytes forwarded for checking, nothing published without a valid signature, receipts, other numbers |
| `test_parsing.py`       | Payload → messages: text/non-text, several entries/changes, E.164, timestamps, contact names, malformed shapes                                             |
| `test_real_payloads.py` | Webhooks in the exact shape Meta sent them (anonymized)                                                                                                    |
| `test_verification.py`  | The configuration-service client: requests sent, 404 / other statuses / network errors                                                                     |
| `test_publisher.py`     | Data, attributes, ordering key, failures (ordering key resumed), emulator setup, emulator round trip                                                       |
| `test_routes.py`        | Health check, error shape, API docs                                                                                                                        |

## Project structure

```
messaging-ingester/
├── app/
│   ├── __init__.py       # create_app(): FastAPI app, logging, error handlers, routers; startup sets up the emulator
│   ├── config.py         # settings (constants + environment variables)
│   ├── errors.py         # JSON error bodies, the same as messaging-service's
│   ├── schemas.py        # pydantic response models
│   ├── routes.py         # GET / health check
│   ├── webhook.py        # GET/POST /webhook/{business_id}
│   ├── verification.py   # client for configuration-service's verify-token / verify-signature
│   ├── parsing.py        # Meta payload → InboundMessage (the Pub/Sub contract)
│   └── publisher.py      # Pub/Sub publisher + emulator setup
├── scripts/pull_debug.py # print what was published (emulator)
├── tests/
├── Dockerfile
├── run.py                # dev server
└── requirements.txt
```
