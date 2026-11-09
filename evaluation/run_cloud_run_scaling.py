"""Verify Cloud Run scale-out and replacement with the disposable canary service.

Run recovery while the canary has min=1/max=1, then update it to max=3 and run
scaleout. Results contain process IDs, statuses and timings, never auth tokens.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def gcloud_token() -> str:
    launcher = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not launcher:
        raise RuntimeError("gcloud CLI is required to invoke the private canary")
    result = subprocess.run([launcher, "auth", "print-identity-token", "--quiet"],
                            capture_output=True, text=True, check=True)
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty identity token")
    return token


def request(base: str, path: str, token: str | None, method: str = "GET",
            timeout: float = 45) -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    status, payload, error = None, {}, None
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers, method=method),
                                    timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raw, error = b"", type(exc).__name__
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    return {"status": status, "instance_id": payload.get("instance_id"),
            "error": error, "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def recovery(base: str, token: str | None, deadline_s: float) -> dict:
    baseline = [request(base, "/health", token) for _ in range(5)]
    ids = {row["instance_id"] for row in baseline if row["status"] == 200 and row["instance_id"]}
    if len(ids) != 1 or any(row["status"] != 200 for row in baseline):
        return {"status": "inconclusive", "reason": "Expected one healthy baseline instance (max=1)",
                "baseline": baseline}
    old_id = next(iter(ids))
    failed = request(base, "/fail", token, method="POST")
    if failed["status"] != 202 or failed["instance_id"] != old_id:
        return {"status": "fail", "reason": "Failure request did not reach the baseline instance",
                "baseline_id": old_id, "failure_request": failed}
    # Wait until the canary's 200 ms exit timer has fired before checking replacement.
    time.sleep(0.5)
    started = time.perf_counter()
    probes = []
    while time.perf_counter() - started < deadline_s:
        row = request(base, "/health", token, timeout=10)
        probes.append(row)
        if row["status"] == 200 and row["instance_id"] and row["instance_id"] != old_id:
            return {"status": "pass", "old_instance_id": old_id,
                    "new_instance_id": row["instance_id"],
                    "recovery_seconds": round(time.perf_counter() - started, 3),
                    "probe_errors": sum(item["status"] != 200 for item in probes),
                    "probes": probes}
        time.sleep(0.5)
    return {"status": "fail", "reason": "No replacement instance before deadline",
            "old_instance_id": old_id, "probes": probes}


def scaleout(base: str, token: str | None, requests: int, rounds: int, delay_ms: int) -> dict:
    baseline = request(base, "/health", token)
    if baseline["status"] != 200 or not baseline["instance_id"]:
        return {"status": "fail", "reason": "Baseline health check failed", "baseline": baseline}
    rows = []
    path = "/work?" + urllib.parse.urlencode({"delay_ms": delay_ms})
    for _ in range(rounds):
        barrier = threading.Barrier(requests + 1)

        def one() -> dict:
            barrier.wait()
            return request(base, path, token)

        with concurrent.futures.ThreadPoolExecutor(max_workers=requests) as pool:
            futures = [pool.submit(one) for _ in range(requests)]
            barrier.wait()
            rows.extend(future.result() for future in futures)
    ids = sorted({row["instance_id"] for row in rows if row["status"] == 200 and row["instance_id"]})
    errors = sum(row["status"] != 200 for row in rows)
    return {"status": "pass" if len(ids) > 1 and errors == 0 else "fail",
            "baseline_instance_id": baseline["instance_id"],
            "distinct_instance_count": len(ids), "instance_ids": ids,
            "requests": len(rows), "errors": errors,
            "p95_ms": sorted(row["latency_ms"] for row in rows)[(len(rows) * 95 + 99) // 100 - 1],
            "responses": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Canary Cloud Run service root URL")
    parser.add_argument("--phase", choices=("recovery", "scaleout"), required=True)
    parser.add_argument("--gcloud-token", action="store_true", help="Get a private-service ID token from gcloud")
    parser.add_argument("--allow-remote", action="store_true", help="Allow contacting the hosted canary")
    parser.add_argument("--requests", type=int, default=12, help="Concurrent requests per scaleout round")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--delay-ms", type=int, default=2500)
    parser.add_argument("--recovery-deadline-s", type=float, default=60)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "cloud-run-scaling.json")
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        parser.error("--url must have an http(s) scheme and hostname")
    if parsed.hostname.lower() not in LOCAL_HOSTS and not args.allow_remote:
        parser.error("Hosted canary requests require --allow-remote")
    if not 2 <= args.requests <= 30 or not 1 <= args.rounds <= 5 or not 0 <= args.delay_ms <= 3000:
        parser.error("Use 2-30 concurrent requests, 1-5 rounds and 0-3000 ms delay")
    if args.recovery_deadline_s <= 0:
        parser.error("Recovery deadline must be positive")
    token = gcloud_token() if args.gcloud_token else None
    base = args.url.rstrip("/")
    measured = (recovery(base, token, args.recovery_deadline_s) if args.phase == "recovery"
                else scaleout(base, token, args.requests, args.rounds, args.delay_ms))
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "host": parsed.hostname,
              "phase": args.phase, **measured}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{args.phase}: {result['status']}")
    if args.phase == "recovery" and result["status"] == "pass":
        print(f"Replacement observed in {result['recovery_seconds']:.2f}s; "
              f"{result['probe_errors']} failed probe(s)")
    elif args.phase == "scaleout":
        print(f"{result.get('distinct_instance_count', 0)} distinct instances; "
              f"{result.get('errors', '?')} errors in {result.get('requests', 0)} requests")
    print(f"Results: {args.output.resolve()}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
