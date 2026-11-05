"""Gate 2.5 — entity #2 from template, day-one measured, books separate."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_entities import EntityError, day_one_checklist, instantiate
from dyn_ledger import WorkLedger


class TestEntities(unittest.TestCase):

    def test_instantiate_separate_books(self):
        e1 = instantiate("ent-001", day=1)
        e2 = instantiate("ent-002", day=1)
        self.assertIsNot(e1.book, e2.book)
        self.assertIsNot(e1.treasury, e2.treasury)
        self.assertNotEqual(e1.receipts[0]["digest"], e2.receipts[0]["digest"])
        e1.book.post("1000", "3000", 1_000_000, "genesis top-up", day=1)
        self.assertGreater(len(e1.book.journal), len(e2.book.journal))
        self.assertNotEqual(e2.book.journal_digest(), e1.book.journal_digest())

    def test_day_one_checklist_green(self):
        led = WorkLedger()
        ent = instantiate("ent-002", day=1)
        report = day_one_checklist(ent, led=led)
        self.assertEqual(len(report["steps"]), 10)
        self.assertTrue(all(s["ok"] for s in report["steps"]))
        self.assertIsInstance(report["elapsed_ms"], int)
        self.assertTrue(report["digest"])

    def test_checklist_anchors_into_ledger(self):
        led = WorkLedger()
        ent = instantiate("ent-002", day=1)
        day_one_checklist(ent, led=led)
        anchors = [e for e in led.entries if e["kind"] == "anchor"]
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["agent"], "ent-002")
        self.assertTrue(led.verify_chain()["ok"])

    def test_checklist_without_ledger_still_measured(self):
        ent = instantiate("ent-002", day=1)
        report = day_one_checklist(ent)
        self.assertEqual(report["steps"][8]["step"], "anchor")
        self.assertIn("skipped in unit mode", report["steps"][8]["detail"])

    def test_bad_entity_id_refused(self):
        with self.assertRaises(EntityError):
            instantiate("../not-an-entity", day=1)


if __name__ == "__main__":
    unittest.main()
