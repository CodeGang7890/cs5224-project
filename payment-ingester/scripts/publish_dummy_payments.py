"""Publishes random dummy payment events to the local Pub/Sub emulator, as payment-ingester will.

    python scripts/publish_dummy_payments.py             # 5 events
    python scripts/publish_dummy_payments.py --count 20

Each message's data is JSON `{"payment_id": "pay_…", "status": "success" | "fail"}` (processing-service
consumes them). Talks to the emulator at PUBSUB_EMULATOR_HOST (default localhost:8085, docker-compose's),
never to Google Cloud. The topic is created by docker-compose's pubsub-init; this creates it too if missing.
"""

import argparse
import json
import os
import random
import secrets

# Before importing the client library, so it never reaches the real Google Cloud.
os.environ.setdefault('PUBSUB_EMULATOR_HOST', 'localhost:8085')

from google.api_core import exceptions as google_exceptions  # noqa: E402
from google.cloud import pubsub_v1  # noqa: E402

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'local-project')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'payment-events')
STATUSES = ('success', 'fail')


def dummy_payment() -> dict:
    return {'payment_id': f'pay_{secrets.token_hex(8)}', 'status': random.choice(STATUSES)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--count', type=int, default=5, help='how many events to publish (default 5)')
    args = parser.parse_args()

    publisher = pubsub_v1.PublisherClient()
    topic = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)
    try:
        publisher.create_topic(request={'name': topic}, timeout=10)
    except google_exceptions.AlreadyExists:
        pass
    print(f'Publishing {args.count} dummy payment events to {topic} (emulator {os.environ["PUBSUB_EMULATOR_HOST"]})')
    for _ in range(args.count):
        payment = dummy_payment()
        message_id = publisher.publish(
            topic, json.dumps(payment).encode(), payment_id=payment['payment_id'], status=payment['status']
        ).result(timeout=10)
        print(f'  {payment["payment_id"]}  {payment["status"]:<7}  (Pub/Sub message {message_id})')


if __name__ == '__main__':
    main()
