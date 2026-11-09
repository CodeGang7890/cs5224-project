"""Replay selected failure and duplicate-delivery tests as a reproducible fault matrix.

These tests inject provider, publisher, consumer and delivery failures with mocks. They
do not prove exactly-once delivery in the deployed Pub/Sub system.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "messaging-ingester": [
        "tests.test_webhook.ReceiveWebhookTests.test_publish_failure_is_503_so_meta_retries",
        "tests.test_webhook.ReceiveWebhookTests.test_bad_or_missing_signature_is_401_and_nothing_is_published",
    ],
    "messaging-service": [
        "tests.test_consumer.HandleTests.test_a_failure_nacks_so_it_is_redelivered",
        "tests.test_inbound.InboundTests.test_a_duplicate_is_answered_once",
        "tests.test_outbox.OutboxTests.test_a_failure_is_retried_with_a_growing_delay_then_given_up",
        "tests.test_inbound_bundling.BundlingTests.test_a_message_arriving_while_an_order_is_placed_gets_its_own_reply",
    ],
    "processing-service": [
        "tests.test_consumer.HandleTests.test_a_failure_nacks_so_it_is_redelivered",
        "tests.test_consumer.HandleTests.test_an_invoice_that_could_not_be_sent_yet_is_nacked_so_it_is_redelivered",
        "tests.test_payments.PaymentFlowTests.test_a_repeated_event_makes_the_receipt_again_after_a_failed_upload",
    ],
    "payment-ingester": [
        "tests.TestFastAPIApp.test_webhook_invalid_token",
        "tests.TestCreatePaymentApi.test_create_payment_still_succeeds_if_the_created_event_cannot_be_published",
    ],
    "notification-job": [
        "tests.test_email_sender.SendEmailTests.test_which_failures_are_worth_retrying",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "faults.json")
    args = parser.parse_args()
    interpreter = str(Path(args.python).resolve())
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "cases": [], "total": 0, "passed": 0}
    for service, names in CASES.items():
        env = os.environ.copy()
        temporary = ROOT / "evaluation" / "results" / "tmp" / service
        temporary.mkdir(parents=True, exist_ok=True)
        env.update({"TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary)})
        completed = subprocess.run([interpreter, "-m", "unittest", "-v", *names], cwd=ROOT / service,
                                   capture_output=True, text=True, errors="replace", env=env, timeout=180)
        log = completed.stdout + completed.stderr
        match = re.search(r"Ran (\d+) tests? in", log)
        count = int(match.group(1)) if match else 0
        passed = completed.returncode == 0 and count == len(names)
        result["cases"].append({"service": service, "selected": names, "run": count,
                                "status": "pass" if passed else "fail",
                                "failure_tail": "" if passed else "\n".join(log.splitlines()[-25:])})
        result["total"] += count
        result["passed"] += count if passed else 0
        print(f"{service}: {count}/{len(names)} fault cases {'passed' if passed else 'FAILED'}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}")
    return 0 if result["passed"] == result["total"] == sum(map(len, CASES.values())) else 1


if __name__ == "__main__":
    raise SystemExit(main())
