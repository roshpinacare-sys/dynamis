"""Gate 1.2 — benchmark receipts are measured, tiered, and challenge-verified."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_bench import (BenchError, assign_tier, challenge_device,
                       run_benchmark, verify_receipt)


class TestBench(unittest.TestCase):

    def test_receipt_measures_throughput(self):
        r = run_benchmark("dev-001", day=1)
        self.assertIn("throughput_us", r)
        self.assertGreater(r["throughput_us"], 0)
        self.assertGreater(r["total_ms"], 0)
        self.assertEqual(len(r["kernels"]), 3)

    def test_receipt_rehash_verifies(self):
        r = run_benchmark("dev-001")
        verify_receipt(r)                       # must not raise

    def test_tampered_receipt_refused(self):
        r = run_benchmark("dev-001")
        forged = dict(r)
        forged["throughput_us"] = 999_999_999   # inflate the measurement
        with self.assertRaises(BenchError):
            verify_receipt(forged)

    def test_tier_matches_measured_thresholds(self):
        self.assertEqual(assign_tier(10), "T1")
        self.assertEqual(assign_tier(10_000), "T2")
        self.assertEqual(assign_tier(49_999), "T3")
        self.assertEqual(assign_tier(50_000), "T4")

    def test_tier_in_receipt_cannot_exceed_measurement(self):
        r = run_benchmark("dev-001")
        self.assertEqual(r["tier"], assign_tier(r["throughput_us"]))

    def test_challenge_issues_digests(self):
        r = run_benchmark("dev-001")
        c = challenge_device(r)
        self.assertEqual(len(c["expected_digests"]), 3)
        self.assertTrue(all(d["digest"] for d in c["expected_digests"]))

    def test_forged_receipt_refused_before_challenge(self):
        r = run_benchmark("dev-001")
        r2 = dict(r, tier="T4", throughput_us=1)     # lie about capacity
        with self.assertRaises(BenchError):
            challenge_device(r2)

    def test_bad_device_id_refused(self):
        with self.assertRaises(BenchError):
            run_benchmark("../not-a-device")


if __name__ == "__main__":
    unittest.main()
