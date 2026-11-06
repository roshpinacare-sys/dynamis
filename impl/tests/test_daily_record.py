"""The daily record: dated measured facts, deterministic, gap-honest."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from daily_record import RECORD, build_record  # noqa: E402


class TestDailyRecord(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.out = Path(cls._td.name)
        cls.rec = build_record("2026-11-06", out_dir=cls.out, seed=20261106,
                               sim_days=2, uptime_fn=lambda: None)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_writes_all_three_artifacts(self):
        d = self.out / "2026-11-06"
        for name in ("dashboard.html", "metrics.txt", "summary.json"):
            self.assertTrue((d / name).exists(), name)
            self.assertGreater((d / name).stat().st_size, 100, name)

    def test_uptime_gap_is_named_not_zeroed(self):
        """No measurement here — the gap stays null, never a fabricated zero."""
        self.assertIsNone(self.rec["uptime_24h"])

    def test_uptime_embedded_when_measured(self):
        stub = {"beats": 24, "completed": 24, "succeeded": 24,
                "uptime_bps": 10000}
        with tempfile.TemporaryDirectory() as td:
            rec = build_record("2026-11-06", out_dir=Path(td), seed=20261106,
                               sim_days=2, uptime_fn=lambda: stub)
        self.assertEqual(rec["uptime_24h"], stub)
        # the measured uptime is a stamped fact: its presence changes the digest
        self.assertNotEqual(rec["record_digest"], self.rec["record_digest"])

    def test_record_is_truthful(self):
        self.assertEqual(self.rec["record"], RECORD)
        self.assertTrue(self.rec["law19_ok"])
        self.assertTrue(self.rec["heartbeat_ok"])
        self.assertGreater(self.rec["jobs_settled"], 0)
        self.assertEqual(self.rec["emitted_dyn_mu"],
                         self.rec["settled_revenue_muc"] * 400)
        self.assertTrue(self.rec["record_digest"])

    def test_dashboard_states_invariant_holds(self):
        html = (self.out / "2026-11-06" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("INVARIANT HOLDS", html)

    def test_deterministic_seed_reproduces_numbers(self):
        """Same seed, same date → same measured numbers, digest identical
        modulo the generation timestamp."""
        rec2 = build_record("2026-11-06", out_dir=self.out / "again",
                            seed=20261106, sim_days=2, uptime_fn=lambda: None)
        strip = lambda r: {k: v for k, v in r.items()   # noqa: E731
                           if k not in ("record_digest", "generated_at")}
        self.assertEqual(strip(self.rec), strip(rec2))
        self.assertEqual(self.rec["record_digest"], rec2["record_digest"])


if __name__ == "__main__":
    unittest.main()
