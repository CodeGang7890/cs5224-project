"""Capture Cloud Run instance counts and Pub/Sub backlog for a technical load run.

Requires gcloud authentication with Monitoring Viewer. Monitoring samples arrive with
a delay, so run this at least two minutes after the load test finishes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def query(project: str, token: str, metric: str, resource_filter: str,
          start: datetime, end: datetime) -> list[dict]:
    filter_text = f'metric.type="{metric}" AND {resource_filter}'
    params = {"filter": filter_text, "interval.startTime": start.isoformat(),
              "interval.endTime": end.isoformat(), "view": "FULL", "pageSize": "1000"}
    base = f"https://monitoring.googleapis.com/v3/projects/{urllib.parse.quote(project)}/timeSeries"
    series = []
    page_token = None
    while True:
        page_params = dict(params)
        if page_token:
            page_params["pageToken"] = page_token
        url = base + "?" + urllib.parse.urlencode(page_params)
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        series.extend(payload.get("timeSeries", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            return series


def samples(series: list[dict]) -> list[dict]:
    by_time: dict[str, int] = defaultdict(int)
    for item in series:
        for point in item.get("points", []):
            stamp = point["interval"]["endTime"]
            by_time[stamp] += int(point["value"].get("int64Value", 0))
    return [{"time": stamp, "count": value} for stamp, value in sorted(by_time.items())]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--service", required=True, help="Cloud Run service name")
    parser.add_argument("--subscription", help="Pub/Sub subscription name")
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "cloud_metrics.json")
    args = parser.parse_args()
    if args.minutes < 3:
        parser.error("--minutes must be at least 3 because Monitoring data is delayed")
    gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not gcloud:
        parser.error("gcloud CLI is required to read Cloud Monitoring metrics")
    token = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True,
                           text=True, check=True).stdout.strip()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=args.minutes)
    instance_series = query(args.project, token, "run.googleapis.com/container/instance_count",
                            f'resource.type="cloud_run_revision" AND resource.labels.service_name="{args.service}"',
                            start, end)
    result = {"project": args.project, "service": args.service,
              "window_start": start.isoformat(), "window_end": end.isoformat(),
              "instance_count": samples(instance_series), "subscription": args.subscription}
    if args.subscription:
        backlog_series = query(args.project, token,
                               "pubsub.googleapis.com/subscription/num_unacked_messages_by_region",
                               f'resource.type="pubsub_subscription" AND resource.labels.subscription_id="{args.subscription}"',
                               start, end)
        result["unacked_messages"] = samples(backlog_series)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    peak = max((item["count"] for item in result["instance_count"]), default=None)
    print(f"Cloud Run peak instances: {peak if peak is not None else 'no data'}")
    if args.subscription:
        backlog = result["unacked_messages"]
        print(f"Pub/Sub latest unacked: {backlog[-1]['count'] if backlog else 'no data'}")
    print(f"Results: {args.output.resolve()}")
    return 0 if result["instance_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
