"""Prints (and acknowledges) the messages waiting on the debug subscription of the local emulator.

Run it inside the ingester container, which has PUBSUB_EMULATOR_HOST set:

    docker compose exec messaging-ingester python scripts/pull_debug.py

Each message is shown once: pulling acknowledges it.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import pubsub_v1  # noqa: E402

from app import config  # noqa: E402


def main() -> None:
    if not os.getenv('PUBSUB_EMULATOR_HOST'):
        sys.exit('PUBSUB_EMULATOR_HOST is not set: this script is for the local Pub/Sub emulator.')
    subscriber = pubsub_v1.SubscriberClient()
    path = subscriber.subscription_path(config.GCP_PROJECT_ID, config.PUBSUB_DEBUG_SUBSCRIPTION)
    response = subscriber.pull(request={'subscription': path, 'max_messages': 100}, timeout=10)
    if not response.received_messages:
        print(f'No messages waiting on {path}.')
        return
    for received in response.received_messages:
        message = received.message
        print(json.dumps({
            'ordering_key': message.ordering_key,
            'attributes': dict(message.attributes),
            'data': json.loads(message.data),
        }, indent=2, ensure_ascii=False))
    subscriber.acknowledge(request={'subscription': path, 'ack_ids': [r.ack_id for r in response.received_messages]})
    print(f'{len(response.received_messages)} message(s) pulled and acknowledged.')


if __name__ == '__main__':
    main()
