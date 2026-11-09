"""Measure HTTP webhook ACKs, authenticated replies, and optional tenant probes.

No credentials or response bodies are written to the result. Remote targets require
--allow-remote because valid webhook payloads may enqueue work and incur charges.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import hmac
import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def load_secret(name: str | None) -> str | None:
    if name is None:
        return None
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Environment variable {name} is empty or missing")
    return value


def target_is_remote(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Target URL must use http or https and include a hostname")
    return parsed.hostname.lower() not in LOCAL_HOSTS


def request_once(url: str, method: str, template: str | None, headers: dict[str, str],
                 bearer: str | None, meta_secret: str | None, timeout: float,
                 scheduled: float | None = None) -> dict:
    request_id = uuid.uuid4().hex
    body = None
    if template is not None:
        body = (template.replace("{{request_id}}", request_id)
                .replace("{{timestamp}}", str(int(time.time())))).encode("utf-8")
    actual_headers = dict(headers)
    if bearer:
        actual_headers["Authorization"] = f"Bearer {bearer}"
    if meta_secret:
        if body is None:
            raise ValueError("Meta signing requires --body-template")
        signature = hmac.new(meta_secret.encode(), body, hashlib.sha256).hexdigest()
        actual_headers["X-Hub-Signature-256"] = f"sha256={signature}"
    if body is not None:
        actual_headers.setdefault("Content-Type", "application/json")
    started = time.perf_counter()
    status, error = None, None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=actual_headers,
                                                           method=method), timeout=timeout) as response:
            status = response.status
            response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = type(exc).__name__
    return {"status": status, "error": error,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "dispatch_lag_ms": round(max(0, started - scheduled) * 1000, 3) if scheduled else None}


def summarize(rows: list[dict], expected: set[int]) -> dict:
    durations = [row["latency_ms"] for row in rows]
    failures = sum(row["status"] not in expected for row in rows)
    return {"requests": len(rows), "unexpected": failures,
            "error_rate": failures / len(rows) if rows else None,
            "p50_ms": percentile(durations, 0.50), "p95_ms": percentile(durations, 0.95),
            "max_ms": max(durations, default=None),
            "max_dispatch_lag_ms": max((row["dispatch_lag_ms"] or 0 for row in rows), default=None),
            "status_counts": {str(code): sum(row["status"] == code for row in rows)
                              for code in sorted({row["status"] for row in rows}, key=lambda x: str(x))},
            "client_errors": {name: sum(row["error"] == name for row in rows)
                              for name in sorted({row["error"] for row in rows if row["error"]})}}


def probe_loop(url: str, headers: dict[str, str], bearer: str | None, timeout: float,
               interval: float, stop: threading.Event, rows: list[dict]) -> None:
    while not stop.is_set():
        rows.append(request_once(url, "GET", None, headers, bearer, None, timeout))
        stop.wait(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Webhook, sandbox-message, or read-only API endpoint")
    parser.add_argument("--method", default="POST", choices=("GET", "POST"))
    parser.add_argument("--body-template", type=Path, help="UTF-8 body; {{request_id}} is unique per request")
    parser.add_argument("--header", action="append", default=[], help="KEY: VALUE; keep credentials in env vars")
    parser.add_argument("--bearer-env", help="Environment variable containing an auth token")
    parser.add_argument("--meta-secret-env", help="Environment variable containing Meta app secret for HMAC")
    parser.add_argument("--xendit-token-env", help="Environment variable containing Xendit callback token")
    parser.add_argument("--rates", default="1", help="Comma-separated requests/s, e.g. 1,5,10,25,50")
    parser.add_argument("--seconds-per-step", type=float, default=10)
    parser.add_argument("--max-requests", type=int, default=100, help="Explicitly raise for a larger run")
    parser.add_argument("--workers", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--expected-status", default="200", help="Comma-separated HTTP statuses")
    parser.add_argument("--slo", choices=("webhook", "reply", "none"), default="none")
    parser.add_argument("--error-rate-target", type=float, help="Optional maximum fraction of unexpected responses")
    parser.add_argument("--probe-url", help="Read-only endpoint for the other tenant during the burst")
    parser.add_argument("--probe-bearer-env", help="Other tenant's token environment variable")
    parser.add_argument("--probe-expected-status", default="200")
    parser.add_argument("--allow-remote", action="store_true", help="Explicitly allow requests outside localhost")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "load.json")
    args = parser.parse_args()
    if (target_is_remote(args.url) or args.probe_url and target_is_remote(args.probe_url)) and not args.allow_remote:
        parser.error("Remote targets require --allow-remote; real webhooks can enqueue paid work")
    if args.method == "GET" and args.body_template:
        parser.error("GET must not have a body template")
    if args.seconds_per_step <= 0 or args.max_requests < 1 or args.workers < 1 or args.timeout <= 0:
        parser.error("Duration, request limit, workers and timeout must be positive")
    if args.error_rate_target is not None and not 0 <= args.error_rate_target <= 1:
        parser.error("--error-rate-target must be between 0 and 1")
    try:
        rates = [float(item) for item in args.rates.split(",")]
        expected = {int(item) for item in args.expected_status.split(",")}
        probe_expected = {int(args.probe_expected_status)}
        if any(rate <= 0 for rate in rates):
            raise ValueError("Rates must be positive")
        counts = [max(1, round(rate * args.seconds_per_step)) for rate in rates]
        if sum(counts) > args.max_requests:
            raise ValueError(f"Run would send {sum(counts)} requests; raise --max-requests explicitly")
        headers = {}
        for item in args.header:
            name, value = item.split(":", 1)
            headers[name.strip()] = value.strip()
        bearer = load_secret(args.bearer_env)
        meta_secret = load_secret(args.meta_secret_env)
        xendit_token = load_secret(args.xendit_token_env)
        if xendit_token:
            headers["x-callback-token"] = xendit_token
        probe_bearer = load_secret(args.probe_bearer_env)
        template = args.body_template.read_text(encoding="utf-8") if args.body_template else None
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    result = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "target_host": urllib.parse.urlsplit(args.url).hostname,
              "profile": args.slo, "steps": [], "probe": None}
    baseline: list[dict] = []
    probe_rows: list[dict] = []
    all_response_rows: list[dict] = []
    stop = threading.Event()
    if args.probe_url:
        for _ in range(5):
            baseline.append(request_once(args.probe_url, "GET", None, {}, probe_bearer, None, args.timeout))
            time.sleep(1)
        probe_thread = threading.Thread(target=probe_loop,
                                      args=(args.probe_url, {}, probe_bearer, args.timeout, 1, stop, probe_rows),
                                      daemon=True)
        probe_thread.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for rate, count in zip(rates, counts):
                start = time.perf_counter()
                futures = []
                for index in range(count):
                    scheduled = start + index / rate
                    delay = scheduled - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    futures.append(pool.submit(request_once, args.url, args.method, template, headers,
                                               bearer, meta_secret, args.timeout, scheduled))
                rows = [future.result() for future in concurrent.futures.as_completed(futures)]
                all_response_rows.extend(rows)
                summary = summarize(rows, expected)
                summary["rate_per_second"] = rate
                summary["duration_seconds"] = round(time.perf_counter() - start, 3)
                result["steps"].append(summary)
                print(f"{rate:g}/s: {summary['requests']} requests, {summary['unexpected']} unexpected, "
                      f"p95={summary['p95_ms']:.0f} ms", flush=True)
    finally:
        stop.set()
        if args.probe_url:
            probe_thread.join(timeout=args.timeout + 1)
    all_rows = result["steps"]
    total = sum(step["requests"] for step in all_rows)
    unexpected = sum(step["unexpected"] for step in all_rows)
    result["total_requests"] = total
    result["unexpected"] = unexpected
    result["error_rate"] = unexpected / total if total else None
    result["p95_ms"] = percentile([row["latency_ms"] for row in all_response_rows], 0.95)
    if args.probe_url:
        result["probe"] = {"baseline": summarize(baseline, probe_expected),
                           "during_burst": summarize(probe_rows, probe_expected)}
    target = {"webhook": 1000, "reply": 10000}.get(args.slo)
    if target is not None:
        # A p95 from fewer than 20 requests is too unstable to claim an SLO pass.
        result["slo_target_ms"] = target
        result["slo_status"] = "inconclusive" if total < 20 else (
            "pass" if unexpected == 0 and result["p95_ms"] < target else "fail")
    if args.error_rate_target is not None:
        result["error_rate_target"] = args.error_rate_target
        result["error_rate_status"] = "pass" if result["error_rate"] <= args.error_rate_target else "fail"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}")
    return 0 if unexpected == 0 and result.get("slo_status") != "fail" and result.get("error_rate_status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
