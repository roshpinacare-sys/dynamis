"""Tests: the Agent Kit — the reference client agents copy."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_kit import AgentKit, identity_op, resolve_dispute, witness_verdict, demo
from dynamis_core import EmissionLedger, usds


class TestAgentKit(unittest.TestCase):
    def test_demo_end_to_end(self):
        self.assertEqual(demo(), 0)   # honest paid, fraud caught, invariants hold

    def test_identity_op_shape_and_law17(self):
        op = identity_op("agent-honest-1", "honest.persona", "hsm:kr-honest", day=3)
        self.assertEqual(op["id"], "dyn.id.v1")
        self.assertIn("represents nothing else", op["json"]["claim"])
        self.assertNotIn("hsm:kr-honest", str(op))   # fingerprint only, never the keyref

    def test_enrollment_without_receipts_refused(self):
        k = AgentKit("agent-x1", "x.persona", "hsm:kr-x")
        with self.assertRaises(ValueError):
            k.enroll_device("device-1", [])

    def test_settle_refuses_unsettled_machine(self):
        ek = AgentKit("entity-x1", "rail.x", "hsm:kr-e", role="entity")
        k = AgentKit("agent-y1", "y.persona", "hsm:kr-y")
        m = ek.open_job("job-kit-1", "ent-001", {"task": "t"}, usds(500), 10, "env-ops-1")
        led = EmissionLedger()
        with self.assertRaises(ValueError):
            k.settle(m, led=led)          # OPEN/FUNDED can never settle (Law 19)

    def test_full_lifecycle_both_agents(self):
        ek = AgentKit("entity-x1", "rail.x", "hsm:kr-e", role="entity")
        honest = AgentKit("agent-h1", "h.persona", "hsm:kr-h", stake_dyn_mu=2_500_000)
        fraud = AgentKit("agent-f1", "f.persona", "hsm:kr-f", stake_dyn_mu=2_500_000)
        led = EmissionLedger()

        m = ek.open_job("job-kit-2", "ent-001", {"task": "t"}, usds(500), 10, "env-ops-1")
        honest.claim(m, ("a" * 64,), "b" * 64)
        self.assertEqual(witness_verdict(m, 1, reexec_matches=True), "pass")
        r = honest.settle(m, led=led)
        self.assertEqual(r["payout_muc"], usds(475))
        self.assertTrue(r["chain_ok"])

        m2 = ek.open_job("job-kit-3", "ent-001", {"task": "t"}, usds(500), 10, "env-ops-1")
        fraud.claim(m2, ("0" * 64,), "1" * 64)
        self.assertEqual(witness_verdict(m2, 1, reexec_matches=False), "fail")
        resolve_dispute(m2)
        self.assertEqual(m2.state, "REFUNDED")
        self.assertEqual(m2.worker_payout_muc, 0)
        self.assertTrue(led.invariant_holds())


if __name__ == "__main__":
    unittest.main()
