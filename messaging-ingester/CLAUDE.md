# CLAUDE.md: messaging-ingester

Guidance for Claude Code when working in `messaging-ingester/`.

## What this is

A **FastAPI** service (port **8002**) that receives Meta's WhatsApp Cloud API webhooks and publishes each customer message to **Pub/Sub** (topic `whatsapp-inbound-messages`) for `../messaging-service`. The README has the endpoints, status codes and the **Pub/Sub message contract**. Keep the README in sync when any of them change.

## Design decisions (the user chose these; don't change them without asking)

- **No secrets, no database, no cache.** Each business's WhatsApp settings live in `../configuration-service` (`configuration_app.WhatsAppConfiguration`). The ingester asks configuration-service's internal API on **every** request, which answers **yes/no only** (secrets never leave it):

  - `POST /api/internal/whatsapp/<id>/verify-token/` with `{verify_token}`
  - `POST …/verify-signature/` with the **raw webhook body forwarded unchanged** (`application/octet-stream`) and Meta's `X-Hub-Signature-256` header

  Both answer `{valid, phone_number_id}`, with the `X-Internal-Api-Key` header (`INTERNAL_API_KEY`).

- **One Callback URL per business:** `/webhook/{business_id}`.
- **Never re-serialize the body before the signature check.** `raw_body()` reads the bytes, `verification.verify_signature()` forwards them as-is, and only then is the body parsed with `json.loads`.
- **Status codes are Meta's retry signal:** anything but 200 makes Meta retry.
  - 401 bad or missing signature (nothing published)
  - 404 business not connected
  - 400 signed but not JSON
  - 503 configuration-service or Pub/Sub unavailable
  - 403 / 422 for the handshake
- Only changes whose `metadata.phone_number_id` equals the business's (returned by verify-signature) are published. `statuses` (receipts) are ignored. Malformed items are skipped, never a crash.
- **Pub/Sub:** data = `InboundMessage.to_dict()` JSON; attributes `business_id`, `phone_number_id`, `message_id`; ordering key = the customer's E.164 number (`PublisherOptions(enable_message_ordering=True)`; after a failed publish, `resume_publish` that key). The route waits for every future; any failure → `PublishError` → 503. Consumers dedupe on `message_id`.

## Stack

| Package                                              | Notes                                                                                                                                                                                                              |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **FastAPI 0.142** (`<0.143`, like messaging-service) | App factory `create_app()`; routers per module with tags; Swagger at `/docs`; ReDoc off. Error bodies copied from messaging-service (`app/errors.py`): `{code, status, message}` and 422 `{code, status, errors}`. |
| **uvicorn**                                          | `run.py` (dev, reload) and the Dockerfile `CMD` (`${PORT:-8002}` for Cloud Run).                                                                                                                                   |
| **httpx 0.28**                                       | `ConfigurationServiceClient` (sync, `transport=` injectable for tests).                                                                                                                                            |
| **google-cloud-pubsub 2.x**                          | `PubSubPublisher` (lazy client, so tests and building the app need no credentials); `ensure_emulator_resources()` runs at startup only with `PUBSUB_EMULATOR_HOST`.                                                |
| **httpx2**                                           | Tests only (Starlette's `TestClient`). The `httpx` and `httpx2` loggers are set to WARNING in `create_app`.                                                                                                        |

Routes are plain `def`s (blocking HTTP and Pub/Sub calls run in FastAPI's thread pool). The raw body comes from the async dependency `raw_body()`.

## Structure

- `app/config.py`: settings. Constants plus env (`CONFIGURATION_SERVICE_URL`, `INTERNAL_API_KEY`, `GCP_PROJECT_ID`, `PUBSUB_TOPIC`; the library reads `PUBSUB_EMULATOR_HOST`).
- `app/webhook.py`: the routes. Dependencies `get_verifier()` / `get_publisher()` (`lru_cache` singletons) are swapped in tests with `app.dependency_overrides`.
- `app/verification.py`: 200 → `Verification`; 404 → `BusinessNotConnectedError`; any other status, bad JSON or `httpx.HTTPError` → `VerificationUnavailableError`.
- `app/parsing.py`: `parse_webhook(payload, business_id, phone_number_id)` → `ParseResult(messages, skipped)`.
- `app/publisher.py`: `Publisher` protocol, `PubSubPublisher`, `ensure_emulator_resources()`.
- `scripts/pull_debug.py`: pull + ack from `whatsapp-inbound-debug` (emulator).

## Local stack (repo root `docker-compose.yml`)

- `pubsub-emulator` (`gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators`, port 8085, in memory).
- `messaging-ingester` (built image, no source mount, so rebuild after changes: `docker compose up -d --build messaging-ingester`).
- configuration-service has `DJANGO_ALLOWED_HOSTS` including `configuration-service`, so the ingester's requests aren't rejected.

## Tests (must pass before finishing a change)

The host Python is 3.8 (too old). Run the tests in the image with the source mounted, from the repo root:

```bash
docker compose up -d pubsub-emulator   # so EmulatorIntegrationTests runs too
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD/messaging-ingester:/app" messaging-ingester python -m unittest -v
```

- Fakes live in `tests/helpers.py` (`FakeVerifier`, `FakePublisher`, payload builders).
- Never call real Meta, configuration-service or Google Cloud from tests.
- `tests/test_real_payloads.py` holds webhooks in Meta's exact shape, anonymized. Keep real phone numbers and names out of tests.
- zsh doesn't word-split variables: pass test labels as separate arguments, not in one `$VAR`.
