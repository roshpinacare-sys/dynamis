"""Tests: dyn.engine.v1 — the work-loop engine (docs/12-work-loop.md).

The loop must be drivable end to end on a real artifact, and it must fail closed:
no evidence, no settlement; bad artifact, no payout; no step-skipping.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))
sys.path.insert(0, str(IMPL / "tests"))

import jsonschema  # noqa: E402

from dyn_engine import (ARTIFACT_INVOICE_PARSER, EngineError, WorkLoop,
                        generate_invoice_batch, ground_truth)  # noqa: E402

BAD_ARTIFACT = ARTIFACT_INVOICE_PARSER.replace(
    '+ ln["qty"] * ln["unit_cents"]', '+ ln["qty"] * ln["unit_cents"] + 1')


def new_loop(tmp: Path, name: str = "job-test-1") -> WorkLoop:
    loop = WorkLoop(tmp / name)
    loop.job_new(job_id=name, entity_id="ent-001", revenue_ref="env-ops-001",
                 value_muc=500_000_000, deadline_day=10, seed=30161, count=500,
                 currencies=("USD", "EUR"), buyer_count=20, day=1)
    return loop


class TestHappyPath(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.loop = new_loop(self.tmp)
        art = self.tmp / "parser.py"
        art.write_text(ARTIFACT_INVOICE_PARSER)
        self.loop.work(art)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_open_creates_valid_job_folder(self):
        job = self.loop.log["job"]
        schema = json.loads((IMPL.parent / "schemas" / "job.schema.json").read_text())
        jsonschema.validate(job, schema)
        self.assertTrue((self.tmp / "job-test-1" / "inputs" / "batch.json").is_file())
        self.assertEqual(self.loop.log["status"], "working")

    def test_check_passes_with_four_evidence_records(self):
        res = self.loop.check(day=2)
        self.assertEqual(res["overall"], "PASS")
        self.assertEqual(res["records"], 4)
        recs = [json.loads(p.read_text()) for p in
                (self.tmp / "job-test-1" / "evidence").glob("0*.json")]
        self.assertEqual(len(recs), 4)
        for r in recs:
            self.assertIn("limitations", r)      # honesty is part of the contract
            self.assertIn("class" if "class" in r else "cls", r)
            self.assertEqual(r["verdict"], "PASS")

    def test_settle_pays_only_after_evidence(self):
        self.loop.check(day=2)
        res = self.loop.settle(day=10)
        self.assertGreater(res["payout_muc"], 0)
        self.assertGreater(res["emitted_dyn_mu"], 0)   # Law 19: flow → emission
        self.assertTrue(res["chain_ok"])
        self.assertEqual(self.loop.log["status"], "settled")

    def test_post_binds_artifact_bytes(self):
        import hashlib
        self.loop.check(day=2)
        self.loop.settle(day=10)
        wire = self.loop.post(day=10, post_id="post-test-1")
        code = next(e for e in wire["embeds"] if e["kind"] == "code")
        self.assertEqual(code["sha256"],
                         hashlib.sha256(ARTIFACT_INVOICE_PARSER.strip().encode()).hexdigest())
        self.assertTrue((self.tmp / "job-test-1" / "post" / "preview.html").is_file())

    def test_history_seq_strictly_increasing(self):
        self.loop.check(day=2)
        self.loop.settle(day=10)
        seqs = [h["seq"] for h in self.loop.log["history"]]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(set(seqs)), len(seqs))


class TestFailClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _work_and_check(self, artifact: str) -> WorkLoop:
        loop = new_loop(self.tmp, "job-fail-1")
        art = self.tmp / "parser.py"
        art.write_text(artifact)
        loop.work(art)
        loop.check(day=2)
        return loop

    def test_wrong_totals_fail_and_no_settlement(self):
        loop = self._work_and_check(BAD_ARTIFACT)
        self.assertEqual(loop.log["status"], "checked_fail")
        with self.assertRaises(EngineError):
            loop.settle(day=10)

    def test_check_requires_artifact(self):
        loop = WorkLoop(self.tmp / "job-empty-1")
        with self.assertRaises(EngineError):
            loop.check(day=1)                      # not even a folder yet
        new_loop(self.tmp, "job-empty-1")
        with self.assertRaises(EngineError):
            WorkLoop(self.tmp / "job-empty-1").check(day=1)   # open, no artifact

    def test_settle_refuses_without_pass_status(self):
        loop = new_loop(self.tmp, "job-nosettle-1")
        art = self.tmp / "p.py"
        art.write_text(ARTIFACT_INVOICE_PARSER)
        loop.work(art)
        with self.assertRaises(EngineError):       # status working — never checked
            loop.settle(day=10)

    def test_no_step_skipping_after_settle(self):
        loop = self._work_and_check(ARTIFACT_INVOICE_PARSER)
        loop.settle(day=10)
        with self.assertRaises(EngineError):
            loop.settle(day=11)                    # double settle
        with self.assertRaises(EngineError):
            loop.work(self.tmp / "p.py")           # no rework after money moved

    def test_tampered_inputs_refuse_check(self):
        loop = new_loop(self.tmp, "job-tamper-1")
        art = self.tmp / "p.py"
        art.write_text(ARTIFACT_INVOICE_PARSER)
        loop.work(art)
        inp = self.tmp / "job-tamper-1" / "inputs" / "batch.json"
        data = json.loads(inp.read_text())
        data["invoices"][0]["lines"][0]["unit_cents"] = 1
        inp.write_text(json.dumps(data))
        with self.assertRaises(EngineError):
            loop.check(day=2)

    def test_refine_loop_recovers(self):
        loop = new_loop(self.tmp, "job-refine-1")
        bad, good = self.tmp / "bad.py", self.tmp / "good.py"
        bad.write_text(BAD_ARTIFACT)
        good.write_text(ARTIFACT_INVOICE_PARSER)
        loop.work(bad)
        self.assertEqual(loop.check(day=2)["overall"], "FAIL")
        loop.work(good)                            # refine: same folder, new build
        self.assertEqual(loop.check(day=3)["overall"], "PASS")
        res = loop.settle(day=10)                  # only the latest evidence vouches
        self.assertGreater(res["payout_muc"], 0)
        ev_index = loop.log["evidence"]
        for rel in ev_index:
            self.assertEqual(
                json.loads((self.tmp / "job-refine-1" / rel).read_text())["verdict"],
                "PASS")


class TestTarget(unittest.TestCase):
    def test_ground_truth_is_independent_and_exact(self):
        batch = generate_invoice_batch(seed=99, count=50, currencies=("USD", "EUR"),
                                       buyers=5)
        gt = ground_truth_from(batch)
        self.assertEqual(gt["lines"], sum(len(i["lines"]) for i in batch["invoices"]))
        manual = {}
        for inv in batch["invoices"]:
            for ln in inv["lines"]:
                manual[inv["currency"]] = manual.get(inv["currency"], 0) \
                    + ln["qty"] * ln["unit_cents"]
        self.assertEqual(gt["by_currency"], manual)


def ground_truth_from(batch: dict) -> dict:
    """The checker's aggregation reads the persisted input file; for the unit test
    we reuse the same code path via a temp file."""
    import tempfile as tf
    with tf.TemporaryDirectory() as td:
        p = Path(td) / "b.json"
        p.write_text(json.dumps(batch))
        return ground_truth(p)


if __name__ == "__main__":
    unittest.main()
