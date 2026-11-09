"""Ensure scaling evidence requires a replacement or multiple distinct processes."""

import unittest
from unittest.mock import patch

from evaluation.run_cloud_run_scaling import recovery, scaleout


def row(status=200, instance_id="old"):
    return {"status": status, "instance_id": instance_id, "error": None, "latency_ms": 10}


class CloudRunScalingTests(unittest.TestCase):
    @patch("evaluation.run_cloud_run_scaling.time.sleep")
    @patch("evaluation.run_cloud_run_scaling.request")
    def test_recovery_requires_a_new_instance_id(self, mocked_request, _sleep):
        mocked_request.side_effect = [*[row() for _ in range(5)], row(202), row(200, "new")]
        result = recovery("http://localhost:8080", None, 5)
        self.assertEqual((result["status"], result["old_instance_id"], result["new_instance_id"]),
                         ("pass", "old", "new"))

    @patch("evaluation.run_cloud_run_scaling.request", return_value=row())
    def test_one_process_cannot_pass_scaleout(self, _request):
        result = scaleout("http://localhost:8080", None, requests=4, rounds=1, delay_ms=0)
        self.assertEqual((result["status"], result["distinct_instance_count"]), ("fail", 1))


if __name__ == "__main__":
    unittest.main()
