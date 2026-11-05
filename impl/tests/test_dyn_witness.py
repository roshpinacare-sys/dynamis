"""Tests: dyn.witness.v1 — sampled re-execution catches the seeded fraud.

Order of proof: first show the hole is real (a forged folder settles), then
close it (the band catches exactly that folder and the escrow refunds in
full), then the band's discipline (fail-closed overrule, honest FAIL passes
through untouched, unsampled jobs are honestly marked 'not checked'), then
the market integration with a forger in the roster.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_engine import (ARTIFACT_INVOICE_PARSER, EngineError,  # noqa: E402
                        WorkLoop)
from dyn_ledger import ledger_from_rows, load_rows  # noqa: E402
from dyn_market import Market  # noqa: E402
from dyn_witness import (WITNESSES, evidence_digest,  # noqa: E402
                         forge_pass, leader_for, reexecute, resolve, review,
                         sampled)
from dynamis_core import usds  # noqa: E402

BAD = ARTIFACT_INVOICE_PARSER.replace(
    '+ ln["qty"] * ln["unit_cents"]', '+ ln["qty"] * ln["unit_cents"] + 1')


def make_job(root: Path, *, artifact: str = ARTIFACT_INVOICE_PARSER,
             value_usds: int = 250, seed: int = 30161, day: int = 1,
             job_id: str | None = None) -> WorkLoop:
    job_id = job_id or root.name
    loop = WorkLoop(root)
    loop.job_new(job_id=job_id, entity_id="ent-001",
                 revenue_ref="env-ops-001", value_muc=usds(value_usds),
                 deadline_day=day + 7, seed=seed, count=500,
                 currencies=("USD", "EUR"), buyer_count=20, day=day)
    art = root / "incoming.py"
    art.write_text(artifact)
    loop.work(art)
    loop.check(day=day)
    return loop


class TestPrimitives(unittest.TestCase):
    def test_leader_is_deterministic_in_band_and_varies(self):
        for job, day in (("job-a", 1), ("job-b", 3)):
            self.assertEqual(leader_for(job, day), leader_for(job, day))
            self.assertIn(leader_for(job, day), WITNESSES)
        picked = {leader_for(f"job-{i}", d) for i in range(8) for d in (1, 2)}
        self.assertGreater(len(picked), 2)          # not one leader for all

    def test_sampling_deterministic_and_class_scaled(self):
        self.assertEqual(sampled("job-x", "E", 5), True)    # 100%
        hits = [sampled(f"job-s{c}", "C", 9) for c in range(20)]
        self.assertTrue(any(hits) and not all(hits))        # class C: partial
        for job in ("job-q", "job-r"):
            self.assertEqual(sampled(job, "A", 4), sampled(job, "A", 4))

    def test_digest_stable_and_tamper_sensitive(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            loop = make_job(tmp / "job-digest-1", artifact=BAD)
            self.assertEqual(loop.log["status"], "checked_fail")
            d1 = evidence_digest(tmp / "job-digest-1")
            self.assertEqual(d1, evidence_digest(tmp / "job-digest-1"))
            forge_pass(tmp / "job-digest-1")            # flips the FAIL verdict
            self.assertNotEqual(d1, evidence_digest(tmp / "job-digest-1"))
        finally:
            shutil.rmtree(tmp)


class TestTheHoleAndTheBand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_the_hole_is_real_forged_folder_settles(self):
        root = self.tmp / "job-hole-1"
        make_job(root, artifact=BAD)                # honestly fails
        self.assertEqual(WorkLoop(root).log["status"], "checked_fail")
        forge_pass(root)                            # the cheat
        out = WorkLoop(root).settle(day=5, worker_id="agent-cheat")
        self.assertGreater(out["payout_muc"], 0)    # the engine paid a fraud
        self.assertEqual(WorkLoop(root).log["status"], "settled")

    def test_forged_folder_is_caught_and_refunded_in_full(self):
        root = self.tmp / "job-caught-1"
        make_job(root, artifact=BAD)
        forge_pass(root)
        v = resolve(root, day=2, cls="E", worker_id="agent-cheat",
                    force_sample=True)
        self.assertTrue(v["sampled"])
        self.assertFalse(v["matches"])
        self.assertTrue(v["forged"])
        self.assertEqual(v["action"], "refund")
        self.assertEqual(v["refund"]["escrow_back_muc"], usds(250))
        self.assertEqual(v["refund"]["emitted_dyn_mu"], 0)
        loop = WorkLoop(root)
        self.assertEqual(loop.log["status"], "refunded")
        # the record on disk now tells the truth: the real FAIL is reinstalled
        verdicts = [json.loads((root / rel).read_text())["verdict"]
                    for rel in loop.log["evidence"]]
        self.assertIn("FAIL", verdicts)
        self.assertIn("witness", [h["kind"] for h in loop.log["history"]])

    def test_artifact_swap_after_check_is_also_caught(self):
        root = self.tmp / "job-swap-1"
        make_job(root)                              # good artifact, PASS
        self.assertEqual(WorkLoop(root).log["status"], "checked_pass")
        (root / "artifact" / "invoice_parser.py").write_text(BAD)  # swap bytes
        forge_pass(root)                            # ...and present as PASS
        v = resolve(root, day=3, cls="E", worker_id="agent-swap",
                    force_sample=True)
        self.assertFalse(v["matches"])
        self.assertEqual(v["action"], "refund")
        self.assertEqual(WorkLoop(root).log["status"], "refunded")

    def test_honest_pass_passes_review_and_settles(self):
        root = self.tmp / "job-honest-1"
        make_job(root)
        v = resolve(root, day=4, cls="E", worker_id="agent-honest-1",
                    force_sample=True)
        self.assertTrue(v["matches"])
        self.assertFalse(v["forged"])
        self.assertEqual(v["action"], "proceed")
        out = WorkLoop(root).settle(day=10, worker_id="agent-honest-1")
        self.assertGreater(out["payout_muc"], 0)

    def test_honest_fail_reproduces_without_overrule(self):
        root = self.tmp / "job-honest-fail-1"
        make_job(root, artifact=BAD)                # honest FAIL, no forgery
        status_before = WorkLoop(root).log["status"]
        v = review(root, day=5, cls="E", force_sample=True)
        self.assertTrue(v["matches"])               # the evidence is true
        self.assertFalse(v["forged"])
        self.assertEqual(v["reexec_overall"], "FAIL")
        self.assertEqual(WorkLoop(root).log["status"], status_before)
        back = WorkLoop(root).refund(day=5, worker_id="agent-honest-1")
        self.assertEqual(back["escrow_back_muc"], usds(250))

    def test_unsampled_review_is_an_honest_not_checked(self):
        root = self.tmp / "job-unsampled-1"
        make_job(root)
        v = review(root, day=6, cls="A")            # force no-sample path
        self.assertFalse(v["sampled"])
        self.assertIsNone(v["matches"])
        self.assertFalse(v["forged"])
        self.assertEqual(WorkLoop(root).log["status"], "checked_pass")

    def test_overrule_is_fail_closed(self):
        root = self.tmp / "job-refunded-1"
        make_job(root, artifact=BAD)
        loop = WorkLoop(root)
        loop.refund(day=6, worker_id="agent-honest-1")
        with self.assertRaises(EngineError):        # only PASS can be overruled
            loop.witness_overrule(day=6, true_evidence_dir=root / "evidence",
                                  leader="witness-1")
        # and a re-executed PASS set can't overrule anything either
        root2 = self.tmp / "job-pass-1"
        make_job(root2)
        rx = reexecute(root2)
        with self.assertRaises(EngineError):        # no FAIL, no proof
            WorkLoop(root2).witness_overrule(day=6,
                                             true_evidence_dir=Path(rx["evidence_dir"]),
                                             leader="witness-1")


class TestMarketWithWitness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.market = Market(seed=3, witness=True, root=cls.tmp)
        cls.summary = cls.market.run(10)            # seed 3: a forge is caught
        cls.rows = cls.market.stream

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_seeded_forgery_caught_and_laws_hold(self):
        self.assertGreaterEqual(self.summary["forged_caught"], 1)
        self.assertTrue(self.summary["laws"]["forged_evidence_never_paid"])
        presented = {r["job"] for r in self.rows
                     if r["event"] == "check" and r.get("note")}
        caught = {r["job"] for r in self.rows
                  if r["event"] == "witness" and r["forged"]}
        # slipped forgeries are invisible by design — the engine settled them
        # on unsampled evidence. A forger earns ONLY on slips; everything it
        # presented is either caught (refunded) or slipped (settled). docs/07
        # named this risk and its mitigation: re-execution is re-runnable by
        # anyone, on any past job — the clawback sweep is the next step.
        slipped = presented - caught
        settles = {r["job"] for r in self.rows if r["event"] == "settle"
                   and r["agent"] == "agent-forger-1"}
        self.assertEqual(settles, slipped)

    def test_every_caught_forge_shows_as_witness_then_refund(self):
        for r in (x for x in self.rows if x["event"] == "witness" and x["forged"]):
            refund = next(x for x in self.rows if x["event"] == "refund"
                          and x["job"] == r["job"]
                          and "forged evidence" in x.get("reason", ""))
            self.assertEqual(refund["emitted_dyn_mu"], 0)
            self.assertGreater(refund["escrow_back_muc"], 0)

    def test_witness_rows_replay_through_the_ledger(self):
        led = ledger_from_rows(load_rows_from(self.rows))
        v = led.verify_chain()
        self.assertTrue(v["ok"])
        inv = led.invariant()
        self.assertTrue(inv["emitted_eq_revenue"])
        self.assertTrue(inv["refund_emits_nothing"])
        self.assertEqual(
            sum(1 for e in led.entries if e["kind"] == "witness"),
            self.summary["witnessed"])

    def test_default_market_stream_has_no_witness_rows(self):
        m = Market(seed=7)
        s = m.run(4)
        self.assertEqual(sum(1 for r in m.stream if r["event"] == "witness"), 0)
        self.assertEqual(s["witnessed"], 0)
        self.assertEqual(s["forged_caught"], 0)


def load_rows_from(rows: list[dict]) -> list[dict]:
    return rows


if __name__ == "__main__":
    unittest.main()
