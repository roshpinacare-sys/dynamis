"""The witness dry-run: the seal holds, and every attack fails closed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from witness_dryrun import run  # noqa: E402


class TestWitnessDryrun(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.lines = run(jobs=10)
        cls.text = "\n".join(cls.lines)

    def test_verdict_is_green(self):
        self.assertIn("DRY-RUN GREEN — the seal holds and fails closed",
                      self.text)

    def test_every_checkpoint_verifies(self):
        """10 jobs → 40 entries → exactly 3 sealed windows, each OK."""
        self.assertEqual(self.text.count("→ OK"), 3)
        self.assertNotIn("→ FAIL", self.text)

    def test_all_four_attacks_rejected(self):
        self.assertEqual(self.text.count("→ REJECTED"), 4)
        self.assertNotIn("!! ACCEPTED", self.text)
        for attack in ("substituted entry", "forged signature",
                       "thin quorum", "edited payout body"):
            self.assertIn(attack, self.text)

    def test_law19_exact_on_scratch_ledger(self):
        self.assertIn("equal=True", self.text)
        self.assertIn("refunds emit nothing=True", self.text)


if __name__ == "__main__":
    unittest.main()
