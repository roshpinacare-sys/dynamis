"""Gate 3.4 — governance amendment loop, veto-gated, fail-closed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_governance import Amendment, Governance, GovernanceError


class TestGovernance(unittest.TestCase):

    def make(self) -> tuple[Governance, Amendment]:
        canon = {"witnesses": {"active": 7, "standby": 14},
                 "emission": {"treasury_bps": 1_000}}
        am = Amendment("am-001", adr_ref="adr/0006", path="witnesses",
                       patch={"active": 9}, rationale="two more honest devices enrolled")
        return Governance(canon), am

    def run_through_veto(self, g: Governance, am: Amendment) -> None:
        g.propose(am)
        g.simulate(am)
        g.veto(am, veto_keys=True)

    def test_amendment_executes_end_to_end(self):
        g, am = self.make()
        self.run_through_veto(g, am)
        g.execute(am)
        self.assertEqual(am.status, "executed")
        self.assertEqual(g.canon["witnesses"]["active"], 9)
        self.assertTrue(g.log.verify()["ok"])

    def test_execute_without_veto_refused(self):
        g, am = self.make()
        g.propose(am)
        g.simulate(am)
        g.veto(am, veto_keys=False)              # veto denied
        self.assertEqual(am.status, "rejected")
        with self.assertRaises(GovernanceError):
            g.execute(am)
        denied = [r for r in g.log.rows if r["op"] == "veto_denied"]
        self.assertEqual(len(denied), 1)          # the denial stays recorded

    def test_execute_twice_refused(self):
        g, am = self.make()
        self.run_through_veto(g, am)
        g.execute(am)
        with self.assertRaises(GovernanceError):
            g.execute(am)

    def test_sim_required_before_veto(self):
        g, am = self.make()
        g.propose(am)
        with self.assertRaises(GovernanceError):
            g.veto(am, veto_keys=True)

    def test_class_x_path_refused_at_draft(self):
        with self.assertRaises(GovernanceError):
            Amendment("am-x", adr_ref="adr/0001", path="custody.keys",
                      patch={"anything": 1}, rationale="never")

    def test_unknown_path_fails_at_sim(self):
        g, _ = self.make()
        bad = Amendment("am-bad", adr_ref="adr/0006", path="no.such.path",
                        patch={"x": 1}, rationale="typo probe")
        g.propose(bad)
        with self.assertRaises(GovernanceError):
            g.simulate(bad)


if __name__ == "__main__":
    unittest.main()
