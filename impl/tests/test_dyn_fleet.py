"""Gate 3.3 — the fleet: shared crew, committee cadence, read-only rollup."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_entities import instantiate  # noqa: E402
from dyn_fleet import (FleetError, book_revenue_flow, capital_committee,  # noqa: E402
                       consolidated_view, hire_shared_crew)
from dynamis_core.canonical import usds  # noqa: E402


def make_fleet(n: int = 3):
    return [instantiate(f"ent-{i:03d}", day=1) for i in range(1, n + 1)]


class TestFleet(unittest.TestCase):

    def test_fleet_of_three_consolidates(self):
        ents = make_fleet()
        for i, ent in enumerate(ents):
            book_revenue_flow(ent, invoice_id=f"{ent.entity_id}-inv-f1",
                              customer=f"client-{i}", value_muc=usds(100 + i),
                              day=1)
        view = consolidated_view(ents)
        self.assertEqual(view["entities"], 3)
        self.assertTrue(view["all_balanced"])

    def test_rollup_equals_sum_of_parts(self):
        ents = make_fleet()
        values = [usds(120), usds(180), usds(250)]
        for ent, v in zip(ents, values):
            book_revenue_flow(ent, invoice_id=f"{ent.entity_id}-inv-f1",
                              customer="c", value_muc=v, day=1)
        view = consolidated_view(ents)
        per_entity_revenue = sum(p["revenue_muc"] for p in view["per_entity"])
        self.assertEqual(view["revenue_muc"], per_entity_revenue)
        self.assertEqual(view["revenue_muc"], sum(values) * 12 // 10)  # +20% markup
        self.assertGreater(view["revenue_muc"], 0)

    def test_view_is_read_only(self):
        ents = make_fleet()
        for ent in ents:
            book_revenue_flow(ent, invoice_id=f"{ent.entity_id}-inv-f1",
                              customer="c", value_muc=usds(100), day=1)
        before = {e.entity_id: e.book.journal_digest() for e in ents}
        consolidated_view(ents)
        after = {e.entity_id: e.book.journal_digest() for e in ents}
        self.assertEqual(before, after)

    def test_shared_crew_round_robins(self):
        ents = make_fleet()
        roster = [{"agent_id": f"crew-{i}", "role": "worker"} for i in range(6)]
        hired = hire_shared_crew(ents, roster)
        employers = {h["employer"] for h in hired}
        self.assertEqual(len(employers), 3)          # one pool, many employers
        self.assertEqual(len(hired), 6)

    def test_committee_session_recorded(self):
        ents = make_fleet()
        s = capital_committee(ents, day=30, session_id="cc-001")
        self.assertEqual(s["cadence_days"], 30)
        self.assertEqual(len(s["reviewed"]), 3)
        self.assertTrue(s["session_digest"])

    def test_fleet_below_three_refused(self):
        ents = make_fleet(2)
        with self.assertRaises(FleetError):
            consolidated_view(ents)


if __name__ == "__main__":
    unittest.main()
