"""Optional live sandbox latency and cross-tenant authorization checks.

Uses test accounts, creates temporary sandbox chats, and deletes them in finally blocks.
Credentials come only from environment variables and are never saved in results.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * fraction) - 1]


def request(base: str, method: str, path: str, payload: dict | None = None,
            token: str | None = None, timeout: float = 180) -> tuple[int, dict, float]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data=body,
                                                           headers=headers, method=method), timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    elapsed = time.perf_counter() - started
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return status, data if isinstance(data, dict) else {}, elapsed


def credentials(user_env: str, password_env: str) -> tuple[str, str]:
    user, password = os.environ.get(user_env), os.environ.get(password_env)
    if not user or not password:
        raise ValueError(f"Set {user_env} and {password_env} to dedicated test-account credentials")
    return user, password


def login(base: str, user_env: str, password_env: str) -> str:
    user, password = credentials(user_env, password_env)
    status, data, _ = request(base, "POST", "/api/auth/token/", {"username": user, "password": password})
    if status != 200 or not data.get("access"):
        raise RuntimeError(f"Test-account login failed: HTTP {status}")
    return data["access"]


def new_session(base: str, token: str) -> int:
    status, data, _ = request(base, "POST", "/api/chat/sandbox-sessions/",
                              {"display_name": "evaluation-" + uuid.uuid4().hex[:10]}, token)
    if status != 201 or not isinstance(data.get("id"), int):
        raise RuntimeError(f"Could not create a sandbox session: HTTP {status}")
    return data["id"]


def delete_session(base: str, token: str, session_id: int) -> int:
    return request(base, "DELETE", f"/api/chat/sandbox-sessions/{session_id}/", token=token)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Configuration service origin, without /api")
    parser.add_argument("--mode", choices=("reply", "isolation", "both"), default="both")
    parser.add_argument("--samples", type=int, default=20, help="Separate sandbox chats; 20 is the minimum for p95")
    parser.add_argument("--message", default="What is the price of pandan chiffon cake?")
    parser.add_argument("--user-env", default="ANSERA_TEST_USERNAME")
    parser.add_argument("--password-env", default="ANSERA_TEST_PASSWORD")
    parser.add_argument("--other-user-env", default="ANSERA_OTHER_TEST_USERNAME")
    parser.add_argument("--other-password-env", default="ANSERA_OTHER_TEST_PASSWORD")
    parser.add_argument("--allow-live", action="store_true", help="Explicitly allow live LLM calls and test data")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "live_scenarios.json")
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        parser.error("--base-url must be an HTTPS origin")
    if not args.allow_live:
        parser.error("Live tests create sandbox chats and may incur Gemini charges; pass --allow-live")
    if not 1 <= args.samples <= 50:
        parser.error("--samples must be between 1 and 50")
    base = args.base_url.rstrip("/")
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "host": parsed.hostname,
              "mode": args.mode, "reply": None, "isolation": None}
    owner = login(base, args.user_env, args.password_env)
    if args.mode in {"isolation", "both"}:
        other = login(base, args.other_user_env, args.other_password_env)
        session_id = new_session(base, owner)
        result["isolation"] = {"pass": False}
        try:
            post_status, _, _ = request(base, "POST", f"/api/chat/sandbox-sessions/{session_id}/messages/",
                                        {"message": "cross-tenant probe"}, other)
            delete_status = delete_session(base, other, session_id)
            result["isolation"] = {"other_tenant_post_status": post_status,
                                   "other_tenant_delete_status": delete_status,
                                   "pass": post_status == 403 and delete_status == 403}
        finally:
            cleanup_status = delete_session(base, owner, session_id)
            result["isolation"]["owner_cleanup_status"] = cleanup_status
            result["isolation"]["pass"] &= cleanup_status == 204
        print(f"Cross-tenant access: {'PASS' if result['isolation']['pass'] else 'FAIL'}")
    if args.mode in {"reply", "both"}:
        samples = []
        for index in range(args.samples):
            session_id = new_session(base, owner)
            sample = {"status": None, "has_reply": False, "latency_seconds": None,
                      "pass": False, "cleanup_status": None}
            try:
                status, data, elapsed = request(base, "POST", f"/api/chat/sandbox-sessions/{session_id}/messages/",
                                                {"message": args.message}, owner)
                passed = status == 200 and isinstance(data.get("message"), str) and bool(data["message"])
                sample.update({"status": status, "has_reply": bool(data.get("message")),
                               "latency_seconds": round(elapsed, 3), "pass": passed})
                print(f"Reply {index + 1}/{args.samples}: HTTP {status}, {elapsed:.2f}s, "
                      f"{'reply' if data.get('message') else 'no reply'}", flush=True)
            finally:
                sample["cleanup_status"] = delete_session(base, owner, session_id)
                sample["pass"] &= sample["cleanup_status"] == 204
                samples.append(sample)
        latencies = [item["latency_seconds"] for item in samples if item["latency_seconds"] is not None]
        p95 = percentile(latencies, 0.95)
        result["reply"] = {"samples": samples, "count": len(samples), "p95_seconds": p95,
                           "failures": sum(not item["pass"] for item in samples),
                           "slo_status": "inconclusive" if len(samples) < 20 else (
                               "pass" if p95 < 10 and all(item["pass"] for item in samples) else "fail")}
        print(f"Reply p95: {p95:.2f}s ({result['reply']['slo_status']})")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}")
    return 0 if all(item is None or item.get("pass", True) and item.get("slo_status") != "fail"
                    for item in (result["isolation"], result["reply"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
