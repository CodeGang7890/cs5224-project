"""Check Singapore backups and rehearse isolated Cloud Storage / Cloud SQL restores.

The production SQL instance is never overwritten. ``sql-clone`` creates a uniquely
named temporary PITR clone and deletes that clone after checking it. ``objects``
uses only a uniquely named test object in the application bucket.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_PROJECT = "cs5224-ansera"
DEFAULT_REGION = "asia-southeast1"
DEFAULT_INSTANCE = "main-postgres-sg"
DEFAULT_BUCKET = "cs5224-ansera-app-objects-sg"
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)")
OPERATION = re.compile(r"operations/([0-9a-f-]{36})")


def gcloud(*args: str, project: str, timeout: int = 180) -> str:
    executable = shutil.which("gcloud.cmd" if os.name == "nt" else "gcloud")
    if not executable:
        raise RuntimeError("gcloud CLI is not installed or is not on PATH")
    completed = subprocess.run(
        [executable, *args, f"--project={project}"],
        text=True, capture_output=True, timeout=timeout, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"gcloud {' '.join(args[:3])} failed: {completed.stderr.strip()[-500:]}")
    return completed.stdout.strip()


def gcloud_json(*args: str, project: str, timeout: int = 180) -> dict | list:
    return json.loads(gcloud(*args, "--format=json", project=project, timeout=timeout))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_recovery_time(instance: str, project: str) -> datetime:
    output = gcloud("sql", "instances", "get-latest-recovery-time", instance,
                    "--format=json", project=project)
    matches = TIMESTAMP.findall(output)
    if not matches:
        raise RuntimeError("Cloud SQL did not return a latest recoverable timestamp")
    return max(parse_time(value) for value in matches)


def check_config(project: str, region: str, instance: str, bucket: str,
                 max_rpo_minutes: float) -> dict:
    sql = gcloud_json("sql", "instances", "describe", instance, project=project)
    backup = sql.get("settings", {}).get("backupConfiguration", {})
    backups = gcloud_json("sql", "backups", "list", f"--instance={instance}",
                          project=project)
    good_backups = [item for item in backups if item.get("status") == "SUCCESSFUL"]
    storage = gcloud_json("storage", "buckets", "describe", f"gs://{bucket}",
                           project=project)
    soft = storage.get("softDeletePolicy") or storage.get("soft_delete_policy") or {}
    retention = soft.get("retentionDuration") or soft.get("retentionDurationSeconds") or "0s"
    result = {
        "sql_region": sql.get("region"),
        "sql_state": sql.get("state"),
        "sql_backup_enabled": backup.get("enabled") is True,
        "sql_backup_location": backup.get("location"),
        "sql_successful_backups": len(good_backups),
        "sql_pitr_enabled": backup.get("pointInTimeRecoveryEnabled") is True,
        "sql_log_retention_days": backup.get("transactionLogRetentionDays"),
        "storage_location": storage.get("location"),
        "storage_soft_delete_seconds": int(str(retention).removesuffix("s")),
    }
    result["configuration_pass"] = all((
        result["sql_region"] == region, result["sql_state"] == "RUNNABLE",
        result["sql_backup_enabled"], result["sql_backup_location"] == region,
        result["sql_successful_backups"] > 0, result["sql_pitr_enabled"],
        result["storage_location"] == region.upper(),
        result["storage_soft_delete_seconds"] >= 604800,
    ))
    result["rpo_probe_pass"] = False
    if result["sql_pitr_enabled"]:
        try:
            latest = latest_recovery_time(instance, project)
        except RuntimeError as error:
            # This API is documented for unavailable or deleted instances. A
            # healthy instance may report no window; test a dated clone instead.
            result["recovery_window_error"] = str(error)
        else:
            lag = max(0.0, (datetime.now(timezone.utc) - latest).total_seconds() / 60)
            result["latest_recovery_time_utc"] = latest.isoformat()
            result["recovery_point_lag_minutes"] = round(lag, 3)
            result["rpo_probe_pass"] = lag <= max_rpo_minutes
    return result


def object_restore(project: str, bucket: str) -> dict:
    marker = uuid.uuid4().hex
    uri = f"gs://{bucket}/recovery-eval/{marker}.txt"
    payload = f"ansera-recovery-eval:{marker}".encode()
    created = False
    restored = False
    with tempfile.TemporaryDirectory() as temp:
        original = Path(temp) / "original.txt"
        recovered = Path(temp) / "recovered.txt"
        original.write_bytes(payload)
        try:
            gcloud("storage", "cp", str(original), uri, project=project)
            created = True
            metadata = gcloud_json("storage", "objects", "describe", uri,
                                   project=project)
            generation = str(metadata["generation"])
            gcloud("storage", "rm", uri, project=project)
            started = time.monotonic()
            gcloud("storage", "restore", f"{uri}#{generation}", project=project)
            restored = True
            gcloud("storage", "cp", uri, str(recovered), project=project)
            same = hashlib.sha256(payload).digest() == hashlib.sha256(recovered.read_bytes()).digest()
            return {"restored": same, "restore_seconds": round(time.monotonic() - started, 3),
                    "generation": generation, "test_object": uri}
        finally:
            if created and restored:
                # Only the UUID object created above is removed; soft delete retains it.
                gcloud("storage", "rm", uri, project=project)


def sql_clone(project: str, instance: str, max_rto_minutes: float,
              restore_age_minutes: float = 5) -> dict:
    target = f"ansera-recovery-eval-{uuid.uuid4().hex[:10]}"
    existing = gcloud_json("sql", "instances", "list", f"--filter=name={target}",
                            project=project)
    if any(item.get("name") == target for item in existing):
        raise RuntimeError(f"Refusing to reuse existing Cloud SQL instance {target}")
    # For a live instance, test whether this exact recent point is recoverable.
    # get-latest-recovery-time is intended for unavailable/deleted instances.
    recovery_at = datetime.now(timezone.utc) - timedelta(minutes=restore_age_minutes)
    started = time.monotonic()
    attempted = False
    clone_operation = None
    clone_finished = False
    try:
        attempted = True
        try:
            gcloud("sql", "instances", "clone", instance, target,
                   f"--point-in-time={recovery_at.isoformat().replace('+00:00', 'Z')}",
                   "--quiet", project=project, timeout=3600)
        except RuntimeError as error:
            match = OPERATION.search(str(error))
            if not match or "taking longer than expected" not in str(error):
                raise
            clone_operation = match.group(1)
            gcloud("beta", "sql", "operations", "wait", clone_operation,
                   "--timeout=3600", project=project, timeout=3700)
        clone_finished = True
        clone = gcloud_json("sql", "instances", "describe", target, project=project)
        databases = gcloud_json("sql", "databases", "list", f"--instance={target}",
                                 project=project)
        minutes = (time.monotonic() - started) / 60
        return {"clone": target, "source_point_utc": recovery_at.isoformat(),
                "requested_point_lag_minutes": restore_age_minutes,
                "clone_ready_minutes": round(minutes, 3), "clone_state": clone.get("state"),
                "application_database_present": any(db.get("name") == "configuration_service"
                                                    for db in databases),
                "rto_probe_pass": minutes <= max_rto_minutes
                and clone.get("state") == "RUNNABLE"
                and any(db.get("name") == "configuration_service" for db in databases)}
    finally:
        if attempted:
            if clone_operation and not clone_finished:
                # A CLI wait timeout does not cancel the server-side operation.
                gcloud("beta", "sql", "operations", "wait", clone_operation,
                       "--timeout=3600", project=project, timeout=3700)
            try:
                gcloud("sql", "instances", "describe", target, project=project)
            except RuntimeError:
                pass
            else:
                gcloud("sql", "instances", "delete", target, "--quiet",
                       project=project, timeout=3600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "objects", "sql-clone"))
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--instance", default=DEFAULT_INSTANCE)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--max-rpo-minutes", type=float, default=5)
    parser.add_argument("--max-rto-minutes", type=float, default=60)
    parser.add_argument("--restore-age-minutes", type=float, default=5,
                        help="SQL clone point before drill start; 5 minutes probes N7 RPO")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode != "check" and not args.allow_live:
        parser.error("objects and sql-clone change live resources; pass --allow-live")
    if args.mode == "check":
        result = check_config(args.project, args.region, args.instance,
                              args.bucket, args.max_rpo_minutes)
        passed = result["configuration_pass"] and result["rpo_probe_pass"]
    elif args.mode == "objects":
        result = object_restore(args.project, args.bucket)
        passed = result["restored"]
    else:
        result = sql_clone(args.project, args.instance, args.max_rto_minutes,
                           args.restore_age_minutes)
        passed = result["rto_probe_pass"]
    result = {"mode": args.mode, "project": args.project, "timestamp_utc":
              datetime.now(timezone.utc).isoformat(), "pass": passed, **result}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
