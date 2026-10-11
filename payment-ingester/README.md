# payment-ingester

Not built yet (see `TODO.txt`). It will receive Xendit's payment webhooks and publish each payment event to Pub/Sub for processing-service, on port **8001** (reserved).

For now there's a standalone script that publishes random dummy payment events to the local Pub/Sub emulator.

## Pub/Sub message contract

| | |
| --- | --- |
| Topic | `payment-events` (created by docker-compose's `pubsub-init`) |
| Data | JSON `{"payment_id": "pay_3f9c1a2b4d5e6f70", "status": "success"}`, where `status` is `success` or `fail` |
| Attributes | `payment_id`, `status` |

## Publishing dummy payment events

With the stack running (`docker compose up --build`, from the repository root):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python scripts/publish_dummy_payments.py             # 5 events
.venv/bin/python scripts/publish_dummy_payments.py --count 20
```

The script uses the emulator at `PUBSUB_EMULATOR_HOST` (default `localhost:8085`), never Google Cloud. `GCP_PROJECT_ID` (default `local-project`) and `PUBSUB_TOPIC` (default `payment-events`) can be overridden.

processing-service pulls the events and logs each one: `docker compose logs -f processing-service`.
