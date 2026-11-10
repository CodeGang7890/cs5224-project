"""Exercise Pub/Sub dead lettering with disposable resources.

The live mode first checks the two application subscriptions and their IAM bindings, then
creates a separate topic, worker subscription, dead-letter topic, and dead-letter
subscription. No test message is published to an application topic.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

from google.api_core.exceptions import DeadlineExceeded
from google.cloud import pubsub_v1


QUEUES = ("messaging-queue", "payment-queue")
ATTEMPTS = 5


def pull_one(subscriber, subscription: str, timeout: float):
    try:
        messages = subscriber.pull(
            request={"subscription": subscription, "max_messages": 1}, timeout=timeout
        ).received_messages
        return messages[0] if messages else None
    except DeadlineExceeded:
        return None


def check_live_configuration(project: str, project_number: str, publisher, subscriber) -> dict:
    agent = f"serviceAccount:service-{project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
    checked = {}
    for queue in QUEUES:
        worker = subscriber.subscription_path(project, f"{queue}-worker")
        dlq = publisher.topic_path(project, f"{queue}-dlq")
        dlq_sub = subscriber.subscription_path(project, f"{queue}-dlq-sub")
        config = subscriber.get_subscription(request={"subscription": worker})
        assert config.dead_letter_policy.dead_letter_topic == dlq, f"{worker}: wrong dead-letter topic"
        assert config.dead_letter_policy.max_delivery_attempts == ATTEMPTS, f"{worker}: wrong attempt limit"
        assert subscriber.get_subscription(request={"subscription": dlq_sub}).topic == dlq
        topic_policy = publisher.get_iam_policy(request={"resource": dlq})
        worker_policy = subscriber.get_iam_policy(request={"resource": worker})
        assert any(b.role == "roles/pubsub.publisher" and agent in b.members for b in topic_policy.bindings), (
            f"{dlq}: Pub/Sub service agent lacks publisher"
        )
        assert any(b.role == "roles/pubsub.subscriber" and agent in b.members for b in worker_policy.bindings), (
            f"{worker}: Pub/Sub service agent lacks subscriber"
        )
        checked[queue] = {
            "max_delivery_attempts": config.dead_letter_policy.max_delivery_attempts,
            "ack_deadline_seconds": config.ack_deadline_seconds,
            "dead_letter_topic": dlq,
            "service_agent_iam": "pass",
        }
    return checked


def run_delivery(project: str, project_number: str | None, timeout_seconds: int) -> dict:
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    suffix = uuid.uuid4().hex[:12]
    source = publisher.topic_path(project, f"eval-dlq-source-{suffix}")
    dead = publisher.topic_path(project, f"eval-dlq-dead-{suffix}")
    worker = subscriber.subscription_path(project, f"eval-dlq-worker-{suffix}")
    dead_sub = subscriber.subscription_path(project, f"eval-dlq-reader-{suffix}")
    created_topics: list[str] = []
    created_subscriptions: list[str] = []
    start = time.monotonic()
    try:
        for name in (source, dead):
            publisher.create_topic(request={"name": name})
            created_topics.append(name)
        subscriber.create_subscription(request={"name": dead_sub, "topic": dead, "ack_deadline_seconds": 10})
        created_subscriptions.append(dead_sub)
        subscriber.create_subscription(
            request={
                "name": worker,
                "topic": source,
                "ack_deadline_seconds": 10,
                "retry_policy": {"minimum_backoff": {"seconds": 1}, "maximum_backoff": {"seconds": 1}},
                "dead_letter_policy": {"dead_letter_topic": dead, "max_delivery_attempts": ATTEMPTS},
            }
        )
        created_subscriptions.append(worker)

        # The emulator does not implement IAM. Live Pub/Sub needs these grants to count
        # attempts and forward the message. They exist only on disposable resources.
        if project_number:
            agent = f"serviceAccount:service-{project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
            dead_policy = publisher.get_iam_policy(request={"resource": dead})
            dead_policy.bindings.add(role="roles/pubsub.publisher", members=[agent])
            publisher.set_iam_policy(request={"resource": dead, "policy": dead_policy})
            worker_policy = subscriber.get_iam_policy(request={"resource": worker})
            worker_policy.bindings.add(role="roles/pubsub.subscriber", members=[agent])
            subscriber.set_iam_policy(request={"resource": worker, "policy": worker_policy})

        payload = f"dead-letter-evaluation:{suffix}".encode("ascii")
        original_id = publisher.publish(source, payload, evaluation="dead-letter").result(timeout=15)
        observed_attempts = []
        forwarded = None
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = max(1, min(5, deadline - time.monotonic()))
            # Check the DLQ first: Pub/Sub's threshold is best effort, so a message
            # may be forwarded before an exact fifth pull is observable.
            item = pull_one(subscriber, dead_sub, remaining)
            if item:
                if payload not in item.message.data:
                    raise AssertionError("Unexpected payload in isolated dead-letter subscription")
                forwarded = item
                subscriber.acknowledge(request={"subscription": dead_sub, "ack_ids": [item.ack_id]})
                break
            item = pull_one(subscriber, worker, remaining)
            if item:
                assert item.message.message_id == original_id, "Unexpected source message"
                observed_attempts.append(item.delivery_attempt)
                subscriber.modify_ack_deadline(
                    request={"subscription": worker, "ack_ids": [item.ack_id], "ack_deadline_seconds": 0}
                )
            else:
                time.sleep(0.2)

        assert forwarded is not None, f"Message did not reach the dead-letter topic within {timeout_seconds}s"
        assert len(observed_attempts) >= 2, "Insufficient redeliveries observed"
        return {
            "status": "pass",
            "configured_max_delivery_attempts": ATTEMPTS,
            "observed_source_deliveries": len(observed_attempts),
            "delivery_attempt_fields": observed_attempts,
            "forwarded_message_id": forwarded.message.message_id,
            "original_message_id": original_id,
            "seconds": round(time.monotonic() - start, 2),
            "note": "The five-attempt threshold is approximate; observed pulls need not equal five.",
        }
    finally:
        # Delete subscriptions before topics, even after an assertion or API error.
        for name in reversed(created_subscriptions):
            try:
                subscriber.delete_subscription(request={"subscription": name})
            except Exception as exc:  # keep trying the remaining cleanup operations
                print(f"Cleanup needed for subscription {name}: {exc}", file=sys.stderr)
        for name in reversed(created_topics):
            try:
                publisher.delete_topic(request={"topic": name})
            except Exception as exc:
                print(f"Cleanup needed for topic {name}: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="local-project")
    parser.add_argument("--project-number", help="Required in live mode for the Pub/Sub service agent")
    parser.add_argument("--live", action="store_true", help="Use real Pub/Sub with disposable resources")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--output", type=Path, help="Write the result as JSON")
    args = parser.parse_args()
    if args.live:
        if os.getenv("PUBSUB_EMULATOR_HOST"):
            parser.error("Unset PUBSUB_EMULATOR_HOST before running --live")
        if not args.project_number:
            parser.error("--live requires --project-number")
        subscriber = pubsub_v1.SubscriberClient()
        publisher = pubsub_v1.PublisherClient()
        config = check_live_configuration(args.project, args.project_number, publisher, subscriber)
    else:
        if not os.getenv("PUBSUB_EMULATOR_HOST"):
            parser.error("Set PUBSUB_EMULATOR_HOST, or pass --live and --project-number")
        config = None
    result = {
        "project": args.project,
        "mode": "live" if args.live else "emulator",
        "production_configuration": config,
        "isolated_delivery": run_delivery(args.project, args.project_number if args.live else None, args.timeout_seconds),
    }
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
