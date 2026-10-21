"""Publishes dummy payment events to the local Pub/Sub emulator, as payment-ingester will.

    python scripts/publish_dummy_payments.py                    # up to 5 pending orders / bookings
    python scripts/publish_dummy_payments.py --count 20
    python scripts/publish_dummy_payments.py --status fail      # every event a failed payment
    python scripts/publish_dummy_payments.py --reference 3f9c…  # a given payment reference (repeatable)

Each message's data is JSON `{"payment_reference": "<32 hex>", "status": "success" | "fail", "amount": …}`
(processing-service consumes them and checks the amount against the order's / booking's total). By
default the references are those of random orders and bookings still pending payment in
configuration-service's database (docker-compose's PostgreSQL, localhost:5433; POSTGRES_* override
it), and the status is random.

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
    SELECT 'order', oi.id, oi.payment_reference,
           COALESCE(SUM((item ->> 'unit_price')::numeric * (item ->> 'quantity')::numeric), 0)
    FROM checkout_app_orderitem AS oi
    CROSS JOIN LATERAL jsonb_array_elements(oi.order_data -> 'items') AS item
    WHERE oi.order_status = 'pending_payment'
    GROUP BY oi.id, oi.payment_reference
    UNION ALL
    SELECT 'booking', si.id, si.payment_reference,
           (si.schedule_data -> 'service' ->> 'price')::numeric
    FROM checkout_app_scheduleitem AS si
    WHERE si.order_status = 'pending_payment'
"""

BY_REFERENCE = """
    SELECT 'order', oi.id, oi.payment_reference,
           COALESCE(SUM((item ->> 'unit_price')::numeric * (item ->> 'quantity')::numeric), 0)
    FROM checkout_app_orderitem AS oi
    CROSS JOIN LATERAL jsonb_array_elements(oi.order_data -> 'items') AS item
    WHERE oi.payment_reference = %s
    GROUP BY oi.id, oi.payment_reference
    UNION ALL
    SELECT 'booking', si.id, si.payment_reference,
           (si.schedule_data -> 'service' ->> 'price')::numeric
    FROM checkout_app_scheduleitem AS si
    WHERE si.payment_reference = %s
"""


def connection():
    return psycopg.connect(
        dbname=os.getenv('POSTGRES_DB', 'configuration_service'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5433')),
    )


def pending_payments() -> list[tuple[str, int, str, float]]:
    """(kind, id, payment_reference, total) of every order / booking waiting for its payment."""
    with connection() as conn:
        return [(kind, item_id, reference, float(total)) for kind, item_id, reference, total in conn.execute(PENDING_PAYMENTS)]


def payments_by_references(references: list[str]) -> list[tuple[str, int, str, float]]:
    found = []
    with connection() as conn:
        for reference in references:
            rows = conn.execute(BY_REFERENCE, (reference, reference)).fetchall()
            if not rows:
                print(f'  No order or booking has payment reference {reference}; skipping it.')
                continue
            kind, item_id, _, total = rows[0]
            found.append((kind, item_id, reference, float(total)))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--count', type=int, default=5, help='how many pending orders / bookings to pay (default 5)')
    parser.add_argument('--status', choices=STATUSES, help='the status of every event (default: random)')
    parser.add_argument('--reference', action='append', help='publish for this payment reference instead (repeatable)')
    args = parser.parse_args()

    if args.reference:
        targets = payments_by_references(args.reference)
    else:
        targets = pending_payments()
        if not targets:
            parser.exit(1, 'No order or booking is pending payment.\n')
        targets = random.sample(targets, min(args.count, len(targets)))
        if len(targets) < args.count:
            print(f'Only {len(targets)} orders / bookings are pending payment.')

    if not targets:
        return

    publisher = pubsub_v1.PublisherClient()
    topic = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)
    try:
        publisher.create_topic(request={'name': topic}, timeout=10)
    except google_exceptions.AlreadyExists:
        pass
    print(f'Publishing {len(targets)} dummy payment events to {topic} (emulator {os.environ["PUBSUB_EMULATOR_HOST"]})')
    for kind, item_id, reference, amount in targets:
        status = args.status or random.choice(STATUSES)
        event = {'payment_reference': reference, 'status': status, 'amount': amount}
        message_id = publisher.publish(
            topic, json.dumps(event).encode(), payment_reference=reference, status=status
        ).result(timeout=10)
        what = f'{kind} #{item_id}' if item_id else kind
        print(f'  {reference}  {status:<7}  {amount:>10.2f}  {what:<12}  (Pub/Sub message {message_id})')


if __name__ == '__main__':
    main()
