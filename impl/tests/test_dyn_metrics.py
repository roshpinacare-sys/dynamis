"""Tests: dyn.metrics.v1 — validation metrics computed from the market stream.

Law 4 (measured, or it did not happen) applied to the growth story: the six
metrics in docs/13 §4 must be *computed* from the stream, agree with the
market's own summary, never divide by zero, and replay identically.
"""
import io
import contextlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_market import Market  # noqa: E402
from dyn_metrics import compute_metrics, load_stream, main, report  # noqa: E402


class TestMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.stream_path = cls.tmp / "market.jsonl"
        cls.summary = Market(seed=7).run(6, out=cls.stream_path)
        cls.rows, cls.loaded_summary = load_stream(cls.stream_path)
        cls.m = compute_metrics(cls.rows)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_jobs_opened_agrees_with_market_summary(self):
        self.assertEqual(self.m["jobs_opened"], self.summary["jobs_opened"])
        self.assertEqual(self.m["days"], self.summary["days"])

    def test_every_job_reaches_a_terminal_state(self):
        opens = {r["job"] for r in self.rows if r["event"] == "open"}
        done = ({r["job"] for r in self.rows if r["event"] == "settle"} |
                {r["job"] for r in self.rows if r["event"] == "refund"})
        self.assertEqual(opens, done)

    def test_pass_rate_by_class_partitions_the_opens(self):
        total = sum(b["opened"] for b in self.m["pass_rate_by_class"].values())
        self.assertEqual(total, self.m["jobs_opened"])
        for b in self.m["pass_rate_by_class"].values():
            self.assertGreater(b["opened"], 0)
            self.assertTrue(0.0 <= b["pass_rate"] <= 1.0)

    def test_failures_caught_matches_refund_share(self):
        refunds = sum(1 for r in self.rows if r["event"] == "refund")
        settles = sum(1 for r in self.rows if r["event"] == "settle")
        self.assertEqual(self.m["failures_caught"],
                         round(refunds / (settles + refunds), 4))

    def test_emission_coupling_positive_and_l19_consistent(self):
        self.assertGreater(self.m["settled_usds"], 0)
        self.assertGreater(self.m["emitted_dyn"], 0)
        self.assertGreater(self.m["dyn_per_settled_usds"], 0)
        settles = [r for r in self.rows if r["event"] == "settle"]
        recomputed = round(
            sum(r["emitted_dyn_mu"] for r in settles) / 1_000_000
            / sum(r["payout_usds"] + r["fee_usds"] for r in settles), 4)
        self.assertEqual(self.m["dyn_per_settled_usds"], recomputed)

    def test_stream_laws_all_hold(self):
        self.assertTrue(all(self.m["laws"].values()),
                        f"laws violated: {self.m['laws']}")

    def test_time_to_first_claim_never_negative(self):
        self.assertGreaterEqual(self.m["time_to_first_claim_days"], 0.0)

    def test_same_seed_replays_identical_metrics(self):
        again = Market(seed=7).run(6)
        rows2, _ = load_stream(self.tmp / "market.jsonl")  # rewrite via new run
        m2 = Market(seed=7)
        # determinism: recompute from a fresh identical run written to disk
        p2 = self.tmp / "market2.jsonl"
        Market(seed=7).run(6, out=p2)
        rows2, _ = load_stream(p2)
        m2 = compute_metrics(rows2)
        self.assertEqual(self.m, m2)

    def test_empty_stream_yields_zeros_without_crashing(self):
        m = compute_metrics([])
        self.assertEqual(m["jobs_opened"], 0)
        self.assertEqual(m["jobs_per_day"], 0.0)
        self.assertEqual(m["dyn_per_settled_usds"], 0.0)
        self.assertEqual(m["failures_caught"], 0.0)
        self.assertTrue(all(m["laws"].values()))    # vacuously true, not false

    def test_report_renders_all_six_metrics(self):
        text = report(self.m)
        for label in ("jobs/day", "time-to-first-claim", "pass rate by class",
                      "failures caught", "payout velocity", "DYN per settled USDS"):
            self.assertIn(label, text)

    def test_cli_exits_zero_and_prints_report(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(self.stream_path)])
        self.assertEqual(rc, 0)
        self.assertIn("laws:", buf.getvalue())
        self.assertIn("stream summary agrees with computed laws: True",
                      buf.getvalue())


if __name__ == "__main__":
    unittest.main()
