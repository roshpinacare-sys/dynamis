"""Tests: dyn.ledger.v1 — the chain-wide work ledger and its checkpoints.

Tamper-evidence by rehash; sealing per the wire spec's pulse cadence; BFT
threshold enforced fail-closed; the Law-19 invariant exact at µ¢ resolution
(no floored-stream residue) on a real market run.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_ledger import (BFT_THRESHOLD, GENESIS, SEAL_EVERY, WorkLedger,
                        ledger_from_rows, load_rows, main,  # noqa: E402
                        report, verify_checkpoint)
from dyn_market import Market  # noqa: E402


def build_ledger(n: int = 30) -> WorkLedger:
    led = WorkLedger()
    for i in range(n):
        led.append(day=i // 3 + 1, kind="work", job_id=f"job-{i:03d}",
                   agent=f"agent-{i % 3}", sha256=f"{'ab' * 8}{i:04d}")
    return led


class TestChain(unittest.TestCase):
    def test_hash_chain_links_and_verifies(self):
        led = build_ledger(10)
        self.assertEqual(led.entries[0]["prev"], GENESIS)
        self.assertTrue(led.verify_chain()["ok"])
        for a, b in zip(led.entries, led.entries[1:]):
            self.assertEqual(b["prev"], a["hash"])

    def test_tamper_breaks_verification_at_the_right_depth(self):
        led = build_ledger(10)
        led.entries[6]["body"]["sha256"] = "f" * 64       # flip a body byte
        v = led.verify_chain()
        self.assertFalse(v["ok"])
        self.assertEqual(v["depth"], 6)

    def test_truncation_tail_is_detectable(self):
        led = build_ledger(10)
        led.entries[-1]["hash"] = GENESIS                  # forged tail
        self.assertFalse(led.verify_chain()["ok"])

    def test_unknown_kind_refused(self):
        with self.assertRaises(ValueError):
            WorkLedger().append(day=1, kind="mint-free-money",
                                job_id="j", agent="a")


class TestMerkleAndCheckpoints(unittest.TestCase):
    def test_merkle_root_deterministic_and_pairwise(self):
        led = build_ledger(5)
        hs = [e["hash"] for e in led.entries]
        r1 = led.merkle_root(hs)
        r2 = led.merkle_root(list(hs))
        self.assertEqual(r1, r2)
        self.assertNotEqual(r1, GENESIS)
        self.assertEqual(led.merkle_root([]), GENESIS)

    def test_checkpoints_seal_every_window_with_bft_sigs(self):
        led = build_ledger(30)
        cps = led.all_checkpoints(day=10)
        self.assertEqual([c["height"] for c in cps], [12, 24])
        for cp in cps:
            self.assertEqual(len(cp["witness_sigs"]), BFT_THRESHOLD)
            self.assertTrue(verify_checkpoint(cp, led)["ok"],
                            verify_checkpoint(cp, led)["why"])
        # state roots chain forward: cp2's root covers cp1's
        self.assertEqual(cps[0]["state_root"], led.merkle_root(
            [e["hash"] for e in led.entries[:12]]))
        self.assertEqual(cps[1]["tx_root"], led.merkle_root(
            [e["hash"] for e in led.entries[12:24]]))

    def test_checkpoint_verification_fails_closed(self):
        led = build_ledger(24)
        cps = led.all_checkpoints()
        short = dict(cps[0], witness_sigs=cps[0]["witness_sigs"][:3])
        self.assertIn("BFT needs", verify_checkpoint(short, led)["why"])
        tampered = dict(cps[0], state_root=GENESIS)
        self.assertIn("state_root mismatch",
                      verify_checkpoint(tampered, led)["why"])
        forged = dict(cps[0], witness_sigs=[
            {"w": "witness-imposter", "s": cps[0]["witness_sigs"][0]["s"]},
            *cps[0]["witness_sigs"][1:]])       # count passes, identity doesn't
        self.assertIn("witness sig invalid",
                      verify_checkpoint(forged, led)["why"])
        self.assertFalse(verify_checkpoint(dict(cps[0], height=13), led)["ok"])

    def test_no_checkpoint_before_a_full_window(self):
        self.assertIsNone(build_ledger(SEAL_EVERY - 1).checkpoint(day=1))


class TestLaw19Exact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.stream = cls.tmp / "m.jsonl"
        cls.summary = Market(seed=7).run(6, out=cls.stream)
        cls.rows = load_rows(cls.stream)
        cls.led = ledger_from_rows(cls.rows)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_invariant_is_exact_at_muc_resolution(self):
        inv = self.led.invariant()
        self.assertEqual(inv["emitted_dyn_mu"],
                         inv["expected_dyn_mu"])          # zero residue
        self.assertTrue(inv["emitted_eq_revenue"])
        settles = [e for e in self.led.entries if e["kind"] == "settle"]
        self.assertEqual(len(settles), self.summary["settled"])
        # the floored stream *couldn't* say this: recompute from rounded rows
        floored = sum(r["payout_usds"] + r["fee_usds"]
                      for r in self.rows if r["event"] == "settle") * 400 * 1_000_000
        self.assertNotEqual(floored, inv["emitted_dyn_mu"])  # residue is real

    def test_refunds_carry_zero_emission_into_the_ledger(self):
        refunds = [e for e in self.led.entries if e["kind"] == "refund"]
        self.assertEqual(len(refunds), self.summary["refunded"])
        self.assertTrue(all(e["body"]["emitted_dyn_mu"] == 0 for e in refunds))
        self.assertTrue(self.led.invariant()["refund_emits_nothing"])

    def test_ledger_replays_the_full_stream(self):
        v = self.led.verify_chain()
        self.assertTrue(v["ok"])
        self.assertEqual(v["depth"], len(self.rows))
        opens = sum(1 for e in self.led.entries if e["kind"] == "open")
        self.assertEqual(opens, self.summary["jobs_opened"])

    def test_cli_roundtrip_from_stream_and_verify(self):
        out = self.tmp / "ledger.jsonl"
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["from-stream", str(self.stream), "--out", str(out)])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn("chain ok: True", text)
        self.assertIn("→ True", text)           # Law 19 exact holds in the report
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = main(["verify", str(out)])
        self.assertEqual(rc2, 0)
        self.assertIn("checkpoint verification:", buf2.getvalue())
        # the written ledger re-verifies standalone: same entries + checkpoints
        written = out.read_text().splitlines()
        self.assertGreater(len(written), len(self.rows))  # entries + checkpoints

    def test_report_names_law19(self):
        self.assertIn("Law 19 exact", report(self.led, []))


if __name__ == "__main__":
    unittest.main()
