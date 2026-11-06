"""Gate 1.1's number: the bps math and the gap-honest fetch path."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from daily_record import measure_uptime  # noqa: E402
from uptime_report import bps_from_runs  # noqa: E402


def run(status: str = "completed", conclusion: str = "success") -> dict:
    return {"status": status, "conclusion": conclusion}


class TestBps(unittest.TestCase):

    def test_all_success_is_10000(self):
        self.assertEqual(bps_from_runs([run() for _ in range(30)]), 10000)

    def test_exact_fraction(self):
        runs = [run() for _ in range(197)] + [run(conclusion="failure")
                                              for _ in range(3)]
        self.assertEqual(bps_from_runs(runs), 9850)

    def test_in_flight_beats_do_not_count(self):
        runs = [run() for _ in range(5)] + [run(status="in_progress")]
        self.assertEqual(bps_from_runs(runs), 10000)

    def test_no_completed_verdict_is_none(self):
        self.assertIsNone(bps_from_runs([run(status="in_progress")]))
        self.assertIsNone(bps_from_runs([]))


class TestMeasureUptime(unittest.TestCase):

    def test_missing_token_is_a_named_gap(self):
        """fetch_runs raises SystemExit for a missing token; SystemExit is a
        BaseException — the gap must stay named (None), not crash the record."""
        with mock.patch("uptime_report.fetch_runs",
                        side_effect=SystemExit("GITHUB_TOKEN required")):
            self.assertIsNone(measure_uptime())

    def test_network_failure_is_a_named_gap(self):
        with mock.patch("uptime_report.fetch_runs",
                        side_effect=OSError("offline")):
            self.assertIsNone(measure_uptime())

    def test_measured_embedding(self):
        runs = [run() for _ in range(197)] + [run(conclusion="failure")
                                              for _ in range(3)]
        with mock.patch("uptime_report.fetch_runs", return_value=runs):
            got = measure_uptime()
        self.assertEqual(got, {"beats": 200, "completed": 200,
                               "succeeded": 197, "uptime_bps": 9850})
        self.assertIsInstance(got["uptime_bps"], int)   # ADR-0007, no floats

    def test_empty_window_is_none(self):
        with mock.patch("uptime_report.fetch_runs", return_value=[]):
            self.assertIsNone(measure_uptime())


if __name__ == "__main__":
    unittest.main()
