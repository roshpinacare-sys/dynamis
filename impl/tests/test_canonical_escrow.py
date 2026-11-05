"""Tests: canonical wire, objects, and the escrow state machine."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamis_core.canonical import (canon, check_id, domain_hash, object_hash,
                                    split_bps, bps_of, usds)
from dynamis_core.objects import AgentPassport, Claim, Eval, Job, PowerAccount
from dynamis_core.escrow import EscrowError, JobMachine


def make_job(escrow=None, deadline=10, cls="C"):
    return Job("job-alpha-1", "ent-001", {"task": "process_invoices", "count": 500},
               usds(1000) if escrow is None else escrow,
               deadline, cls, "env-ops-001")


class TestCanonical(unittest.TestCase):
    def test_usds_unit(self):
        self.assertEqual(usds(1), 1_000_000)          # 1 µ¢ = 10⁻⁶ USDS
        self.assertEqual(usds(40), 40_000_000)

    def test_sorted_keys_deterministic(self):
        a = canon({"b": 1, "a": {"d": 2, "c": 3}})
        b = canon({"a": {"c": 3, "d": 2}, "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, b'{"a":{"c":3,"d":2},"b":1}')

    def test_floats_rejected_anywhere(self):
        self.assertIsInstance(canon({"ok": 1}), bytes)   # integers are fine
        with self.assertRaises(ValueError):
            canon({"nested": [1, 2.5]})
        with self.assertRaises(ValueError):
            canon({"deep": {"x": float("nan")}})

    def test_dataclasses_serialize_canonically(self):
        j = make_job()
        self.assertIsInstance(canon(j), bytes)          # objects hash without ceremony

    def test_domain_separation(self):
        h1 = domain_hash("dyn.job.settle", {"job": "job-alpha-1"})
        h2 = domain_hash("dyn.checkpoint", {"job": "job-alpha-1"})
        self.assertNotEqual(h1, h2)  # a signature over one domain never replays as another
        with self.assertRaises(ValueError):
            domain_hash("EVIL DOMAIN", {})

    def test_split_bps_exact_sum(self):
        parts = split_bps(12345, [4500, 1500, 2000, 1000, 1000])
        self.assertEqual(sum(parts), 12345)
        self.assertEqual(parts[0], 5555)  # 45% with integer floor
        with self.assertRaises(ValueError):
            split_bps(100, [5000, 5000, 1])

    def test_check_id(self):
        self.assertEqual(check_id("job-alpha-1", "x"), "job-alpha-1")
        with self.assertRaises(ValueError):
            check_id("Job!", "x")
        with self.assertRaises(ValueError):
            check_id("ab", "x")  # too short


class TestObjects(unittest.TestCase):
    def test_job_rejects_bad_class(self):
        with self.assertRaises(ValueError):
            make_job(cls="F")

    def test_job_rejects_empty_spec(self):
        with self.assertRaises(ValueError):
            Job("job-x-1", "ent-001", {}, usds(1), 10, "C", "env-ops-001")

    def test_claim_requires_artifacts_and_hex(self):
        with self.assertRaises(ValueError):
            Claim("cl-1", "job-alpha-1", "agent-1", (), "0" * 64, 3)
        with self.assertRaises(ValueError):
            Claim("cl-1", "job-alpha-1", "agent-1", ("nothex",), "0" * 64, 3)

    def test_passport_never_holds_keys(self):
        with self.assertRaises(ValueError):  # raw key material is not a keyref
            AgentPassport("agent-1", "lisa", ("RAWKEYMATERIAL",), ("jobs:read",), "pw-1", 3)
        p = AgentPassport("agent-1", "lisa", ("hsm:kr-1",), ("jobs:read",), "pw-1", 3)
        self.assertTrue(p.keyrefs[0].startswith("hsm:"))

    def test_power_account_integers(self):
        pa = PowerAccount("pw-1", stake_dyn_mu=5_000_000)
        self.assertEqual(pa.erg_credits, 0)
        with self.assertRaises(ValueError):
            PowerAccount("pw-1", stake_dyn_mu=1.5)


class TestEscrow(unittest.TestCase):
    def setUp(self):
        self.job = make_job()
        self.m = JobMachine(self.job, funded_by="ent-001-budget")

    def _deliver(self, m, worker="agent-worker-1"):
        m.fire("claim", worker=worker)
        claim = Claim("cl-1", m.job.job_id, worker,
                      ("a" * 64, "b" * 64), "c" * 64, m.now_day)
        m.fire("deliver", claim=claim)
        m.fire("start_verify")
        return claim

    def test_happy_path_settles_with_fee_split(self):
        m = self.m
        m.fire("fund", from_="ent-001-budget")
        self.assertEqual(m.state, "FUNDED")
        self._deliver(m)
        m.fire("verify_pass", verifier="witness-1")
        self.assertEqual(m.state, "SETTLED")
        self.assertEqual(m.fee_muc, usds(50))            # 5% coordination fee
        self.assertEqual(m.worker_payout_muc, usds(950)) # 95% to the worker
        self.assertTrue(m.verify_chain())

    def test_illegal_transitions_fail_closed(self):
        with self.assertRaises(EscrowError):
            self.m.fire("deliver")          # cannot deliver before claim
        self.m.fire("fund")
        with self.assertRaises(EscrowError):
            self.m.fire("verify_pass", verifier="w")  # nothing delivered
        with self.assertRaises(EscrowError):
            self.m.fire("nonsense_event")

    def test_self_dealing_blocked(self):
        self.m.fire("fund", from_="ent-001-budget")
        with self.assertRaises(EscrowError):
            self.m.fire("claim", worker="ent-001-budget")

    def test_terminal_state_is_absorbing(self):
        self.m.fire("fund")
        self.m.fire("cancel")
        self.assertEqual(self.m.state, "REFUNDED")
        with self.assertRaises(EscrowError):
            self.m.fire("claim", worker="agent-1")
        self.assertEqual(self.m.fee_muc, 0)  # cancel refunds escrow, takes no fee

    def test_deadline_forces_timeout_refund(self):
        m = JobMachine(make_job(deadline=5), "ent-001-budget")
        m.fire("fund")
        m.tick(6)
        with self.assertRaises(EscrowError):  # late settlement is illegal
            self._deliver(m)
        m.timeout()
        self.assertEqual(m.state, "REFUNDED")
        self.assertEqual(m.fee_muc, 0)

    def test_verifier_stall_refunds_not_traps(self):
        m = self.m
        m.fire("fund")
        self._deliver(m)
        m.tick(11)  # past deadline while still DELIVERED
        m.timeout()
        self.assertEqual(m.state, "REFUNDED")

    def test_dispute_paths(self):
        m = self.m
        m.fire("fund")
        self._deliver(m)
        m.fire("dispute", challenger="agent-challenger-1")
        self.assertEqual(m.state, "DISPUTED")
        m.fire("resolve_budget", arbiter="witness-band")
        self.assertEqual(m.state, "REFUNDED")

        m2 = JobMachine(self.job, "ent-001-budget")
        m2.fire("fund")
        self._deliver(m2)
        m2.fire("dispute", challenger="agent-challenger-1")
        m2.fire("resolve_worker", arbiter="witness-band")
        self.assertEqual(m2.state, "SETTLED")

    def test_verify_fail_goes_to_dispute(self):
        m = self.m
        m.fire("fund")
        self._deliver(m)
        m.fire("verify_fail", verifier="witness-1", reason="re-execution mismatch")
        self.assertEqual(m.state, "DISPUTED")

    def test_event_chain_tamper_evident(self):
        m = self.m
        m.fire("fund")
        self._deliver(m)
        m.fire("verify_pass", verifier="witness-1")
        self.assertTrue(m.verify_chain())
        m._events[2]["body"]["worker"] = "agent-attacker-1"  # rewrite history
        self.assertFalse(m.verify_chain())

    def test_time_moves_forward_only(self):
        self.m.tick(3)
        with self.assertRaises(EscrowError):
            self.m.tick(2)


if __name__ == "__main__":
    unittest.main()
