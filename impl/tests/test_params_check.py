"""The params ↔ code mirror: proven, and proven to fail closed."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from params_check import GENESIS, _leaf, check  # noqa: E402

ORIG = GENESIS.read_text(encoding="utf-8")


class TestParamsMirror(unittest.TestCase):

    def test_mirror_holds_today(self):
        """Every mirrored leaf in genesis.yaml equals the code constant."""
        self.assertEqual(check(), [])

    def test_divergence_is_caught(self):
        """Change one ratified value → exactly that divergence, named."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "genesis.yaml"
            tampered = ORIG.replace("coordination_fee_bps: 500",
                                    "coordination_fee_bps: 501")
            self.assertNotEqual(tampered, ORIG)
            p.write_text(tampered, encoding="utf-8")
            fails = check(p)
        self.assertEqual(len(fails), 1)
        self.assertIn("escrow.coordination_fee_bps", fails[0])
        self.assertIn("DIVERGENCE", fails[0])
        self.assertIn("500", fails[0]) and self.assertIn("501", fails[0])

    def test_missing_leaf_fails_closed(self):
        """A leaf that vanished from the params is a finding, not a pass."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "genesis.yaml"
            lines = [ln for ln in ORIG.splitlines()
                     if not ln.strip().startswith("max_post_bytes")]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            fails = check(p)
        self.assertTrue(any("missing leaf: posts.max_post_bytes" in f
                            for f in fails))

    def test_challenge_seeds_tampered(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "genesis.yaml"
            tampered = ORIG.replace("0xBADC0DE", "0xBADC0DF")
            self.assertNotEqual(tampered, ORIG)
            p.write_text(tampered, encoding="utf-8")
            fails = check(p)
        self.assertTrue(any("bench.challenge_seeds" in f for f in fails))

    def test_leaf_locator_is_section_scoped(self):
        """max_daily_usds exists under rail_caps only — the locator must
        resolve it through the section path, not by global grep luck."""
        self.assertEqual(_leaf(ORIG, ("treasury_policy", "rail_caps",
                                      "max_daily_usds")), "50000")
        self.assertEqual(_leaf(ORIG, ("escrow", "coordination_fee_bps")),
                         "500")


if __name__ == "__main__":
    unittest.main()
