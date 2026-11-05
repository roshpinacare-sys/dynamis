"""Gate 2.6 — the treasury is fail-closed, measured."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_treasury import Treasury, TreasuryError, default_state
from dynamis_core.canonical import usds


class TestTreasury(unittest.TestCase):

    def make(self) -> Treasury:
        return Treasury("ent-001", default_state())

    def test_t2_blocked_without_approval(self):
        tr = Treasury("ent-001", default_state(ops_cap_usds=10_000))
        with self.assertRaises(TreasuryError) as ctx:
            tr.execute("spend_capital", usds(2_500), "ops")
        payload = json.loads(ctx.exception.args[0])
        self.assertFalse(payload["decision"]["allowed"])
        self.assertEqual(payload["decision"]["requires"], "human_approval")
        denied = [r for r in tr.journal.rows if r["op"] == "execute_denied"]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0]["amount_muc"], usds(2_500))

    def test_t2_allowed_with_approval(self):
        tr = Treasury("ent-001", default_state(ops_cap_usds=10_000))
        out = tr.execute("spend_capital", usds(2_500), "ops", human_approved=True,
                         memo="regulator-approved")
        self.assertEqual(out["spent_muc"], usds(2_500))
        self.assertEqual(out["envelope_remaining_muc"], usds(10_000) - usds(2_500))

    def test_unknown_kind_denied(self):
        tr = self.make()
        with self.assertRaises(TreasuryError):
            tr.execute("grab_treasury", usds(10), "ops")

    def test_envelope_exhausted_denied(self):
        tr = self.make()
        with self.assertRaises(TreasuryError):
            tr.execute("pay_vendor_bill", usds(600), "ops")   # ops cap is $500

    def test_runway_breach_escalates_to_t2(self):
        st = default_state()
        st.runway_months = 4.0                      # below the 6-month floor
        tr = Treasury("ent-001", st)
        with self.assertRaises(TreasuryError):
            tr.execute("pay_agent_salary", usds(50), "payroll")  # routine kind, now T2

    def test_journal_chain_verifies(self):
        tr = Treasury("ent-001", default_state(ops_cap_usds=10_000))
        tr.execute("pay_vendor_bill", usds(40), "ops")
        with self.assertRaises(TreasuryError):
            tr.execute("spend_capital", usds(2_500), "ops")
        tr.execute("spend_capital", usds(2_500), "ops", human_approved=True)
        v = tr.journal.verify()
        self.assertTrue(v["ok"])
        self.assertEqual(v["rows"], 3)

    def test_decide_is_side_effect_free(self):
        tr = self.make()
        out = tr.decide("post_job_escrow", usds(150), "ops")
        self.assertTrue(out["decision"]["allowed"])
        self.assertEqual(tr.state.envelopes["ops"].spent_muc, 0)  # decided, not executed


if __name__ == "__main__":
    unittest.main()
