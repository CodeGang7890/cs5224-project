"""Run the repository's functional suites and write a reproducible result summary.

Each service runs in its own working directory, as in .github/workflows/ci.yml.
The runner never treats a missing dependency or zero discovered tests as a pass.
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
SERVICES = (
    "configuration-service",
    "messaging-service",
    "messaging-ingester",
    "processing-service",
    "payment-ingester",
    "notification-job",
    "mock_whatsapp",
)
RAN = re.compile(r"Ran (\d+) tests? in ([\d.]+)s")
FAILURES = re.compile(r"(failures|errors|skipped)=(\d+)")


def run_service(service: str, python: str, timeout: int) -> dict:
    command = (
        [python, "manage.py", "test", "--noinput", "--verbosity", "0"]
        if service == "configuration-service"
        else [python, "-m", "unittest", "discover", "-v"]
    )
    result = {"service": service, "command": command, "status": "error", "exit_code": None,
              "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "seconds": None}
    temp_dir = ROOT / "evaluation" / "results" / "tmp" / service
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"TMP": str(temp_dir), "TEMP": str(temp_dir), "TMPDIR": str(temp_dir)})
    try:
        completed = subprocess.run(command, cwd=ROOT / service, capture_output=True,
                                   text=True, errors="replace", timeout=timeout, check=False, env=env)
        log = completed.stdout + completed.stderr
        result["exit_code"] = completed.returncode
        matches = RAN.findall(log)
        if matches:
            result["tests"], result["seconds"] = int(matches[-1][0]), float(matches[-1][1])
        summary = re.search(r"^(?:FAILED|OK)(?: \([^\n]*\))?\s*$", log, re.MULTILINE)
        if summary:
            for key, value in FAILURES.findall(summary.group(0)):
                result[key] = int(value)
        result["status"] = "pass" if completed.returncode == 0 and result["tests"] > 0 else "fail"
        result["tail"] = "\n".join(log.splitlines()[-18:]) if result["status"] != "pass" else ""
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["tail"] = f"Exceeded {timeout} seconds"
    except OSError as exc:
        result["tail"] = str(exc)
    return result


def render_markdown(data: dict) -> str:
    lines = ["# Automated functional evaluation", "", f"Run: {data['timestamp']}",
             f"Commit: `{data['commit']}`", "", "| Service | Result | Tests run | Failures | Errors | Skipped | Time |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in data["services"]:
        seconds = "—" if row["seconds"] is None else f"{row['seconds']:.1f}s"
        lines.append(f"| {row['service']} | {row['status']} | {row['tests']} | {row['failures']} | "
                     f"{row['errors']} | {row['skipped']} | {seconds} |")
    lines.extend(["", "A pass means the service suite exited successfully and discovered at least one test.",
                  "This result covers mocked/local functional behavior; it is not a production availability or load result."])
    for row in data["services"]:
        if row["status"] != "pass":
            lines.extend(["", f"## {row['service']} failure tail", "", "```text", row["tail"], "```"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python with service requirements installed")
    parser.add_argument("--service", action="append", choices=SERVICES, help="Repeat to select suites; default: all")
    parser.add_argument("--timeout", type=int, default=1200, help="Seconds per suite")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "evaluation" / "results")
    args = parser.parse_args()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=False).stdout.strip() or "unknown"
    interpreter = str(Path(args.python).resolve())
    data = {"timestamp": datetime.now(timezone.utc).isoformat(), "commit": commit,
            "python": interpreter, "services": []}
    for service in args.service or SERVICES:
        print(f"Running {service}...", flush=True)
        row = run_service(service, interpreter, args.timeout)
        data["services"].append(row)
        print(f"  {row['status']}: {row['tests']} tests, {row['failures']} failures, "
              f"{row['errors']} errors, {row['skipped']} skipped", flush=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "functional.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.results_dir / "functional.md").write_text(render_markdown(data), encoding="utf-8")
    print(f"Results: {args.results_dir.resolve()}")
    return 0 if all(row["status"] == "pass" for row in data["services"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
