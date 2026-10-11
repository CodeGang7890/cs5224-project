"""Publishes dummy payment events to the local Pub/Sub emulator, as payment-ingester will.

    python scripts/publish_dummy_payments.py                    # up to 5 pending orders / bookings
    python scripts/publish_dummy_payments.py --count 20
    python scripts/publish_dummy_payments.py --status fail      # every event a failed payment
    python scripts/publish_dummy_payments.py --reference 3f9c…  # a given payment reference (repeatable)

Each message's data is JSON `{"payment_reference": "<32 hex>", "status": "success" | "fail"}`
(processing-service consumes them). By default the references are those of random orders and
bookings still pending payment in configuration-service's database (docker-compose's PostgreSQL,
localhost:5433; POSTGRES_* override it), and the status is random.

Talks to the emulator at PUBSUB_EMULATOR_HOST (default localhost:8085, docker-compose's), never to
Google Cloud. The topic is created by docker-compose's pubsub-init; this creates it too if missing.
"""

import argparse
import json
import os
import random

# Before importing the client library, so it never reaches the real Google Cloud.
os.environ.setdefault('PUBSUB_EMULATOR_HOST', 'localhost:8085')

import psycopg  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402
from google.cloud import pubsub_v1  # noqa: E402

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'local-project')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'payment-events')
STATUSES = ('success', 'fail')

PENDING_PAYMENTS = """
    SELECT 'order', id, payment_reference FROM checkout_app_orderitem WHERE order_status = 'pending_payment'
    UNION ALL
    SELECT 'booking', id, payment_reference FROM checkout_app_scheduleitem WHERE order_status = 'pending_payment'
"""


def pending_payments() -> list[tuple[str, int, str]]:
    """(kind, id, payment_reference) of every order / booking waiting for its payment."""
    with psycopg.connect(
        dbname=os.getenv('POSTGRES_DB', 'configuration_service'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5433')),
    ) as connection:
        return connection.execute(PENDING_PAYMENTS).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--count', type=int, default=5, help='how many pending orders / bookings to pay (default 5)')
    parser.add_argument('--status', choices=STATUSES, help='the status of every event (default: random)')
    parser.add_argument('--reference', action='append', help='publish for this payment reference instead (repeatable)')
    args = parser.parse_args()

    if args.reference:
        targets = [('given', None, reference) for reference in args.reference]
    else:
        pending = pending_payments()
        if not pending:
            parser.exit(1, 'No order or booking is pending payment.\n')
        targets = random.sample(pending, min(args.count, len(pending)))
        if len(targets) < args.count:
            print(f'Only {len(targets)} orders / bookings are pending payment.')

    publisher = pubsub_v1.PublisherClient()
    topic = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)
    try:
        publisher.create_topic(request={'name': topic}, timeout=10)
    except google_exceptions.AlreadyExists:
        pass
    print(f'Publishing {len(targets)} dummy payment events to {topic} (emulator {os.environ["PUBSUB_EMULATOR_HOST"]})')
    for kind, item_id, reference in targets:
        event = {'payment_reference': reference, 'status': args.status or random.choice(STATUSES)}
        message_id = publisher.publish(
            topic, json.dumps(event).encode(), payment_reference=reference, status=event['status']
        ).result(timeout=10)
        what = f'{kind} #{item_id}' if item_id else kind
        print(f'  {reference}  {event["status"]:<7}  {what:<12}  (Pub/Sub message {message_id})')


if __name__ == '__main__':
    main()
