"""LLM accuracy benchmark: router, extraction and question handling on a small labelled set.

Each case in datasets/llm_accuracy.json (English customer messages for the three sample businesses) runs
in a fresh sandbox chat. Its messages are sent in order and only the last one is scored, using the
`debug` block the sandbox API returns (the router's intents, the order / booking the flow extracted,
and the question check). Sandbox chats are deleted afterwards. Results hold only aggregate numbers and
per-case verdicts, never credentials or full replies.

Needs the stack running with an LLM behind messaging-service (locally: docker compose + Ollama; see
README.md) and the sample data loaded (the cases use the sample businesses' products, services and FAQs).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    from evaluation.live_scenarios import delete_session, new_session, request
except ImportError:  # run as a script: python evaluation/llm_accuracy.py
    from live_scenarios import delete_session, new_session, request

DATASET = Path(__file__).parent / "datasets" / "llm_accuracy.json"
INTENTS = ("order", "booking", "question", "order_status", "off_topic", "cancel")
USERS = {"kopi": "kopi_owner", "bloom": "bloom_owner", "rally": "rally_owner"}
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
LLM_DOWN = {"HTTP 502", "HTTP 503", "HTTP 504"}   # the LLM errored, unreachable or timed out


def load_cases(path: Path = DATASET) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def score_case(case: dict, status: int, data: dict) -> dict:
    """The verdict for one case from the sandbox reply to its last message (HTTP status and JSON)."""
    if status != 200 or not isinstance(data.get("debug"), dict):
        return {"id": case["id"], "error": f"HTTP {status}"}
    debug = data["debug"]
    got = sorted(debug.get("route", {}).get("intents") or [])
    expected = sorted(case["intents"])
    verdict = {"id": case["id"], "business": case["business"], "expected_intents": expected,
               "got_intents": got, "intents_ok": got == expected}
    after = (debug.get("after") or {}).get("chat_state_data") or {}
    if "items" in case:
        found = {}
        for item in after.get("items") or []:
            found[item.get("name")] = found.get(item.get("name"), 0) + int(item.get("quantity") or 0)
        verdict.update(expected_items=case["items"], got_items=found, extraction_ok=found == case["items"])
    if "service" in case:
        got_service = (after.get("service") or {}).get("name")
        verdict.update(expected_service=case["service"], got_service=got_service,
                       extraction_ok=got_service == case["service"])
    if "question" in case:
        check = debug.get("question_check") or {}
        kind = check.get("kind")
        verdict.update(expected_question=case["question"], got_question=kind, question_ok=kind == case["question"])
        if case["question"] == "unanswered":
            verdict["flagged_to_owner"] = check.get("saved") is not None
        if case.get("facts") and len(case["intents"]) == 1:
            reply = normalise(data.get("message") or "")
            verdict["fact_ok"] = any(normalise(fact) in reply for fact in case["facts"])
    return verdict


def rate(flags: list[bool]) -> dict:
    return {"correct": sum(flags), "total": len(flags), "accuracy": round(sum(flags) / len(flags), 3) if flags else None}


def summarize(verdicts: list[dict]) -> dict:
    """Aggregate the verdicts: router accuracy (exact match and per intent), extraction accuracy, and
    question handling (answerable ones answered, unanswerable ones sent to the owner)."""
    done = [v for v in verdicts if "error" not in v]
    per_intent = {}
    for intent in INTENTS:
        tp = sum(intent in v["expected_intents"] and intent in v["got_intents"] for v in done)
        fp = sum(intent not in v["expected_intents"] and intent in v["got_intents"] for v in done)
        fn = sum(intent in v["expected_intents"] and intent not in v["got_intents"] for v in done)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if tp + fp + fn else None)
        per_intent[intent] = {"tp": tp, "fp": fp, "fn": fn, **{key: None if value is None else round(value, 3)
                              for key, value in (("precision", precision), ("recall", recall), ("f1", f1))}}
    answerable = [v for v in done if v.get("expected_question") == "answered"]
    unanswerable = [v for v in done if v.get("expected_question") == "unanswered"]
    return {
        "cases": len(verdicts), "errors": [v for v in verdicts if "error" in v],
        "router": {"exact_match": rate([v["intents_ok"] for v in done]), "per_intent": per_intent},
        "extraction": {"order_items_and_booking_service": rate([v["extraction_ok"] for v in done if "extraction_ok" in v])},
        "questions": {
            "all_handled_correctly": rate([v["question_ok"] and v.get("flagged_to_owner", True) for v in answerable + unanswerable]),
            "answerable_answered": rate([v["question_ok"] for v in answerable]),
            "answerable_reply_has_fact": rate([v["fact_ok"] for v in answerable if "fact_ok" in v]),
            "unanswerable_sent_to_owner": rate([v["question_ok"] and v["flagged_to_owner"] for v in unanswerable]),
            "unanswerable_guessed_instead": sum(v.get("got_question") == "answered" for v in unanswerable),
        },
    }


def llm_model(messaging_url: str) -> str | None:
    """The model messaging-service answers with (its one-off /chat), or None if it can't be reached.
    Also fails fast, with the reason, when the service is up but its LLM is not."""
    try:
        status, data, _ = request(messaging_url, "POST", "/chat", {"prompt": "Reply with the single word OK."}, timeout=120)
    except OSError:
        return None
    if status == 200 and isinstance(data.get("model"), str):
        return data["model"]
    if f"HTTP {status}" in LLM_DOWN:
        raise RuntimeError(f"messaging-service can't reach its LLM (HTTP {status}): {data.get('detail') or data}")
    return None


def login(base: str, username: str, password: str) -> str:
    status, data, _ = request(base, "POST", "/api/auth/token/", {"username": username, "password": password})
    if status != 200 or not data.get("access"):
        raise RuntimeError(f"Login failed for {username}: HTTP {status}")
    return data["access"]


def run_case(base: str, token: str, case: dict) -> dict:
    session_id = new_session(base, token)
    try:
        status, data = 0, {}
        for message in case["messages"]:
            status, data, _ = request(base, "POST", f"/api/chat/sandbox-sessions/{session_id}/messages/",
                                      {"message": message}, token)
            if status != 200:
                break
        return score_case(case, status, data)
    finally:
        delete_session(base, token, session_id)


def print_summary(summary: dict) -> None:
    show = lambda name, r: print(f"{name:<44}{r['correct']}/{r['total']}"
                                 + (f"  ({r['accuracy']:.1%})" if r["accuracy"] is not None else ""))
    show("Router: exact intent match", summary["router"]["exact_match"])
    for intent, m in summary["router"]["per_intent"].items():
        if m["tp"] + m["fp"] + m["fn"]:
            print(f"  {intent:<14} precision {m['precision']}  recall {m['recall']}  f1 {m['f1']}")
    show("Extraction: items / service correct", summary["extraction"]["order_items_and_booking_service"])
    q = summary["questions"]
    show("FAQ check: answered, or sent to the owner", q["all_handled_correctly"])
    show("  answerable questions answered", q["answerable_answered"])
    show("  ... and the reply has the fact", q["answerable_reply_has_fact"])
    show("  unanswerable questions sent to the owner", q["unanswerable_sent_to_owner"])
    print(f"Unanswerable questions answered anyway (guessed): {q['unanswerable_guessed_instead']}")
    if summary["errors"]:
        print(f"Cases with errors (not scored): {', '.join(e['id'] + ' ' + e['error'] for e in summary['errors'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000", help="configuration-service origin, without /api")
    parser.add_argument("--password-env", default="ANSERA_EVAL_PASSWORD",
                        help="env var with the sample owners' password (locally: 123)")
    parser.add_argument("--business", choices=sorted(USERS), action="append",
                        help="only this sample business (repeatable); default all")
    parser.add_argument("--limit", type=int, help="only the first N cases (a quick check)")
    parser.add_argument("--messaging-url", default="http://localhost:8004",
                        help="messaging-service origin, to read which model answers (it is internal-only when hosted)")
    parser.add_argument("--expect-model", help="stop unless the model's name contains this (e.g. gemini), so Ollama "
                        "numbers are never reported as Gemini's")
    parser.add_argument("--allow-live", action="store_true", help="required for a non-local URL (real LLM charges)")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "llm_accuracy.json")
    args = parser.parse_args()
    host = urllib.parse.urlsplit(args.base_url).hostname
    if host not in LOCAL_HOSTS and not args.allow_live:
        parser.error("A non-local URL creates sandbox chats and may incur LLM charges; pass --allow-live")
    password = os.environ.get(args.password_env)
    if not password:
        parser.error(f"Set {args.password_env} to the sample owners' password")
    base = args.base_url.rstrip("/")
    cases = [c for c in load_cases() if not args.business or c["business"] in args.business][: args.limit]
    try:
        model = llm_model(args.messaging_url.rstrip("/"))
    except RuntimeError as exc:
        parser.exit(2, f"{exc}\n")
    print(f"Model: {model or 'unknown (messaging-service not reachable at ' + args.messaging_url + ')'}")
    if args.expect_model and not (model and args.expect_model.lower() in model.lower()):
        parser.exit(2, f"Expected a model containing {args.expect_model!r}, found {model!r}. Is messaging-service "
                       "running on Gemini? (LLM_PROVIDER=vertex_ai, see messaging-service/README.md)\n")
    tokens, verdicts, llm_down = {}, [], 0
    for index, case in enumerate(cases, 1):
        if case["business"] not in tokens:
            tokens[case["business"]] = login(base, USERS[case["business"]], password)
        verdict = run_case(base, tokens[case["business"]], case)
        verdicts.append(verdict)
        mark = verdict["error"] if "error" in verdict else ("ok" if all(
            verdict.get(k, True) for k in ("intents_ok", "extraction_ok", "question_ok")) else "MISS")
        print(f"[{index}/{len(cases)}] {case['id']}: {mark}", flush=True)
        llm_down = llm_down + 1 if verdict.get("error") in LLM_DOWN else 0
        if llm_down == 3:
            print("\nThree LLM errors in a row: messaging-service can't reach the model (is Ollama running, "
                  "listening on 0.0.0.0, with the model pulled?). Stopping.")
            break
    summary = summarize(verdicts)
    print()
    print_summary(summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "host": host,
                                       "model": model, "summary": summary, "verdicts": verdicts}, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
