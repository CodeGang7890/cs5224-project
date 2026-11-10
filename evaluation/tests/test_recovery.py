"""Guard the live recovery drill's checks and disposable-resource cleanup."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from evaluation import run_recovery


class RecoveryConfigTests(unittest.TestCase):
    def test_fresh_singapore_recovery_point_passes(self):
        now = datetime.now(timezone.utc)
        sql = {"region": "asia-southeast1", "state": "RUNNABLE", "settings": {
            "backupConfiguration": {"enabled": True, "location": "asia-southeast1",
                                    "pointInTimeRecoveryEnabled": True,
                                    "transactionLogRetentionDays": 7}}}
        bucket = {"location": "ASIA-SOUTHEAST1", "soft_delete_policy": {
            "retentionDurationSeconds": "604800"}}
        with mock.patch.object(run_recovery, "gcloud_json", side_effect=[
            sql, [{"status": "SUCCESSFUL"}], bucket,
        ]), mock.patch.object(run_recovery, "latest_recovery_time",
                       return_value=now - timedelta(minutes=2)):
            result = run_recovery.check_config("p", "asia-southeast1", "sql", "bucket", 5)
        self.assertTrue(result["configuration_pass"])
        self.assertTrue(result["rpo_probe_pass"])

    def test_pitr_and_soft_delete_are_required(self):
        sql = {"region": "asia-southeast1", "state": "RUNNABLE", "settings": {
            "backupConfiguration": {"enabled": True, "location": "asia-southeast1",
                                    "pointInTimeRecoveryEnabled": False}}}
        with mock.patch.object(run_recovery, "gcloud_json", side_effect=[
            sql, [{"status": "SUCCESSFUL"}], {"location": "ASIA-SOUTHEAST1"},
        ]), mock.patch.object(run_recovery, "latest_recovery_time") as latest:
            result = run_recovery.check_config("p", "asia-southeast1", "sql", "bucket", 5)
        self.assertFalse(result["configuration_pass"])
        self.assertFalse(result["rpo_probe_pass"])
        latest.assert_not_called()

    def test_live_instance_without_latest_window_reports_unverified(self):
        sql = {"region": "asia-southeast1", "state": "RUNNABLE", "settings": {
            "backupConfiguration": {"enabled": True, "location": "asia-southeast1",
                                    "pointInTimeRecoveryEnabled": True}}}
        bucket = {"location": "ASIA-SOUTHEAST1", "soft_delete_policy": {
            "retentionDurationSeconds": "604800"}}
        with mock.patch.object(run_recovery, "gcloud_json", side_effect=[
            sql, [{"status": "SUCCESSFUL"}], bucket,
        ]), mock.patch.object(run_recovery, "latest_recovery_time",
                       side_effect=RuntimeError("no valid recovery time window")):
            result = run_recovery.check_config("p", "asia-southeast1", "sql", "bucket", 5)
        self.assertTrue(result["configuration_pass"])
        self.assertFalse(result["rpo_probe_pass"])
        self.assertIn("no valid recovery time window", result["recovery_window_error"])


class CloneSafetyTests(unittest.TestCase):
    def test_a_new_clone_is_deleted_after_verification(self):
        with mock.patch.object(run_recovery, "gcloud_json", side_effect=[
            [], {"state": "RUNNABLE"}, [{"name": "configuration_service"}],
        ]), mock.patch.object(run_recovery, "gcloud") as cli:
            result = run_recovery.sql_clone("p", "main-postgres-sg", 60)
        self.assertTrue(result["rto_probe_pass"])
        self.assertEqual(result["requested_point_lag_minutes"], 5)
        self.assertEqual(cli.call_args.args[:4],
                         ("sql", "instances", "delete", result["clone"]))

    def test_slow_clone_waits_for_cloud_operation_before_cleanup(self):
        operation = "858e90e1-82a0-45d7-b6e8-5c3b00000031"
        timeout = RuntimeError("operation https://sqladmin.googleapis.com/operations/"
                               + operation + " is taking longer than expected")
        with mock.patch.object(run_recovery, "gcloud_json", side_effect=[
            [], {"state": "RUNNABLE"}, [{"name": "configuration_service"}],
        ]), mock.patch.object(run_recovery, "gcloud", side_effect=[
            timeout, "", "", "",
        ]) as cli:
            result = run_recovery.sql_clone("p", "main-postgres-sg", 60)
        self.assertTrue(result["rto_probe_pass"])
        self.assertEqual(cli.call_args_list[1].args[:5],
                         ("beta", "sql", "operations", "wait", operation))
        self.assertEqual(cli.call_args_list[-1].args[:4],
                         ("sql", "instances", "delete", result["clone"]))

    def test_existing_clone_name_is_never_deleted(self):
        with mock.patch.object(run_recovery.uuid, "uuid4") as identifier, \
                mock.patch.object(run_recovery, "gcloud_json",
                                  return_value=[{"name": "ansera-recovery-eval-1234567890"}]), \
                mock.patch.object(run_recovery, "gcloud") as cli:
            identifier.return_value.hex = "1234567890abcdef"
            with self.assertRaisesRegex(RuntimeError, "Refusing to reuse"):
                run_recovery.sql_clone("p", "main-postgres-sg", 60)
        cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
