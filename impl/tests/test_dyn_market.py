"""Tests: dyn.market.v1 — the standing market (docs/13-market-flow.md).

The market is the engine left running. The invariants that matter:
fraud is never paid, refunds emit nothing (Law 19), every payout had PASS
evidence, the stream is a complete audit trail, and the same seed replays.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_market import Market  # noqa: E402


def run_market(days=10, seed=7):
    m = Market(seed=seed)
    return m, m.run(days)


class TestStandingMarket(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_job_reaches_a_terminal_state(self):
        m, s = run_market(days=10)
        opens = sum(1 for r in m.stream if r["event"] == "open")
        self.assertEqual(opens, s["jobs_opened"])
        self.assertEqual(opens, s["settled"] + s["refunded"])

    def test_fraud_is_never_paid_and_never_accrues(self):
        _, s = run_market(days=10)
        for aid, a in s["agents"].items():
            if a["behavior"] == "fraud":
                self.assertGreater(a["jobs"], 0)
                self.assertEqual(a["paid_usds"], 0)
                self.assertEqual(a["rc2_muerg"], 0)

    def test_law19_refunds_emit_nothing_settles_emit(self):
        m, _ = run_market(days=10)
        for r in m.stream:
            if r["event"] == "refund":
                self.assertEqual(r["emitted_dyn_mu"], 0)
            if r["event"] == "settle":
                self.assertGreater(r["emitted_dyn_mu"], 0)
                self.assertTrue(r["chain_ok"])

    def test_no_payout_without_pass_evidence(self):
        m, _ = run_market(days=10)
        for r in m.stream:
            if r["event"] == "settle":
                checks = [x for x in m.stream
                          if x["event"] == "check" and x["job"] == r["job"]]
                self.assertTrue(checks)
                self.assertEqual(checks[-1]["overall"], "PASS")

    def test_flaky_agent_refines_in_flow(self):
        m, _ = run_market(days=12, seed=3)
        refined_jobs = {r["job"] for r in m.stream if r["event"] == "refine"}
        self.assertTrue(refined_jobs)                     # the refine loop happens
        for job in refined_jobs:
            seq = [r["event"] for r in m.stream if r.get("job") == job]
            # work → FAIL check → refine → rework → PASS check → settle
            self.assertIn("refine", seq)
            i = seq.index("refine")
            self.assertEqual(seq[i - 1], "check")
            self.assertEqual(seq[i + 1], "work")
            self.assertIn("settle", seq[i:])              # recovery, not abandonment

    def test_same_seed_replays_the_same_market(self):
        _, s1 = run_market(days=8, seed=11)
        _, s2 = run_market(days=8, seed=11)
        self.assertEqual(s1, s2)

    def test_stream_is_a_complete_audit_trail(self):
        m = Market(seed=7, root=self.tmp / "mkt")
        out = self.tmp / "stream.jsonl"
        m.run(6, out=out)
        lines = [json.loads(l) for l in out.read_text().splitlines()]
        self.assertGreater(len(lines), len(m.stream))     # rows + final summary
        rows, summary = lines[:-1], lines[-1]["summary"]
        self.assertEqual(summary["jobs_opened"],
                         sum(1 for r in rows if r["event"] == "open"))
        days = [r["day"] for r in rows]
        self.assertEqual(days, sorted(days))              # time only moves forward
        for r in rows:
            self.assertIn(r["event"],
                          {"open", "work", "check", "refine", "settle", "refund"})

    def test_job_folders_are_recheckable(self):
        m = Market(seed=5, root=self.tmp / "mkt2")
        m.run(4)
        folders = list((self.tmp / "mkt2").iterdir())
        self.assertTrue(folders)
        for f in folders:
            log = json.loads((f / "dyn-job.json").read_text())
            self.assertIn(log["status"], {"settled", "refunded"})
            self.assertTrue(log["evidence"] or log["status"] == "refunded")

    def test_honest_agents_earn_on_every_job(self):
        _, s = run_market(days=10)
        for aid, a in s["agents"].items():
            if a["behavior"] == "honest":
                self.assertGreater(a["jobs"], 0)
                # value floor 120 USDS − 5% fee ⇒ ≥ ~114 per settled job
                self.assertGreaterEqual(a["paid_usds"], a["jobs"] * 114)
                self.assertGreater(a["rc2_muerg"], 0)


if __name__ == "__main__":
    unittest.main()
