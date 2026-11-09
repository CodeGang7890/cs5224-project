"""Check aggregation and percentile math used in the technical report."""

import unittest

from evaluation.cloud_metrics import samples
from evaluation.live_scenarios import percentile
from evaluation.load_test import summarize


class MeasurementTests(unittest.TestCase):
    def test_p95_uses_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 21)), 0.95), 19)

    def test_instance_series_sums_revisions_at_the_same_time(self):
        point = lambda value: {"interval": {"endTime": "2026-11-08T10:00:00Z"},
                               "value": {"int64Value": str(value)}}
        self.assertEqual(samples([{"points": [point(1)]}, {"points": [point(2)]}]),
                         [{"time": "2026-11-08T10:00:00Z", "count": 3}])

    def test_non_200_and_network_errors_are_counted(self):
        rows = [{"status": 200, "error": None, "latency_ms": 100, "dispatch_lag_ms": 0},
                {"status": 503, "error": None, "latency_ms": 200, "dispatch_lag_ms": 0},
                {"status": None, "error": "TimeoutError", "latency_ms": 300, "dispatch_lag_ms": 0}]
        result = summarize(rows, {200})
        self.assertEqual((result["unexpected"], result["error_rate"]), (2, 2 / 3))
        self.assertEqual(result["client_errors"], {"TimeoutError": 1})


if __name__ == "__main__":
    unittest.main()
