"""The gate review: rendered from the registry, joined with real evidence."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from gate_review import (_evidence_counts, _parse_packages, review,  # noqa: E402
                         ROOT)

GATES = ROOT / "specs" / "gates.yaml"
EVIDENCE = ROOT / "specs" / "acceptance" / "EVIDENCE.md"


class TestGateReview(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pkgs = _parse_packages(GATES)
        cls.out = review(GATES, EVIDENCE)

    def test_registry_fully_parsed(self):
        """23 packages across exactly four phases — no silent drops."""
        self.assertEqual(len(self.pkgs), 23)
        self.assertEqual(sorted({p["phase"]["id"] for p in self.pkgs}),
                         [0, 1, 2, 3])

    def test_ids_unique(self):
        ids = [p["id"] for p in self.pkgs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_gate_has_its_row(self):
        for p in self.pkgs:
            self.assertIn(f"| {p['id']} | {p['owner']} |", self.out)
            self.assertIn(p["acceptance"][:40], self.out)

    def test_owner_summary_is_honest(self):
        pending = [p["id"] for p in self.pkgs if "O" in p["owner"]]
        self.assertIn(f"{len(pending)} with an owner act pending", self.out)
        self.assertIn("0.4", pending)       # params ratification
        self.assertIn("3.4", pending)       # amendment loop
        self.assertNotIn("| 2.2 | O", self.out)   # 2.2 is an A-package

    def test_evidence_join_counts_and_quotes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "EVIDENCE.md"
            tmp.write_text(
                "2026-11-05 | 2.2 first measured record | cmd | out | sig\n"
                "2026-11-05 | heartbeat beat | cmd | out | sig\n"
                "not an evidence line\n", encoding="utf-8")
            counts = _evidence_counts(tmp)
            self.assertEqual(list(counts), ["2.2"])
            self.assertEqual(len(counts["2.2"]), 1)
            text = review(GATES, tmp, with_evidence=True)
            self.assertIn("gate 2.2: 2026-11-05 | 2.2 first measured record",
                          text)
            self.assertNotIn("heartbeat beat", text)


if __name__ == "__main__":
    unittest.main()
