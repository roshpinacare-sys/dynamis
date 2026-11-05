"""Gate 3.2 — bond-scored evaluation market, published calibration."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_eval import MIN_BOND_MUC, EvalError, EvalMarket


class TestEvalMarket(unittest.TestCase):

    def make(self) -> EvalMarket:
        return EvalMarket("q-test", ground_truth="pass", day=30)

    def test_overconfident_wrong_burns_bond(self):
        m = self.make()
        m.register("bad-eval", 2_000_000_000)
        m.submit("bad-eval", "fail", 9_600)
        row = m.close()["scored"][0]
        self.assertEqual(row["fee_muc"], 0)
        self.assertGreater(row["burn_muc"], 0)

    def test_correct_verdict_earns_fee(self):
        m = self.make()
        m.register("good-eval", 2_000_000_000)
        m.submit("good-eval", "pass", 8_000)
        row = m.close()["scored"][0]
        self.assertEqual(row["fee_muc"], 2_000_000_000 * 300 // 10000)
        self.assertEqual(row["burn_muc"], 0)

    def test_calibration_report_published_with_worst_bucket(self):
        m = self.make()
        m.register("cal-a", 2_000_000_000)
        m.register("cal-b", 2_000_000_000)
        m.submit("cal-a", "pass", 8_000)
        m.submit("cal-b", "fail", 9_600)          # confidently wrong — must show
        rep = m.close()["report"]
        self.assertGreaterEqual(rep["worst_bucket"]["count"], 1)
        self.assertGreater(rep["worst_bucket"]["mean_score_bps"], 0)
        self.assertGreater(rep["burned_muc"], 0)
        self.assertTrue(rep["no_embarrassment_clause"].startswith("published as measured"))

    def test_no_seat_no_verdict(self):
        m = self.make()
        with self.assertRaises(EvalError):
            m.submit("stranger", "pass", 5_000)

    def test_low_bond_refused(self):
        m = self.make()
        with self.assertRaises(EvalError):
            m.register("cheap-eval", MIN_BOND_MUC - 1)

    def test_one_verdict_per_seat(self):
        m = self.make()
        m.register("dup", 2_000_000_000)
        m.submit("dup", "pass", 8_000)
        with self.assertRaises(EvalError):
            m.submit("dup", "pass", 9_000)

    def test_submissions_after_close_refused(self):
        m = self.make()
        m.register("a", 2_000_000_000)
        m.submit("a", "pass", 8_000)
        m.close()
        with self.assertRaises(EvalError):
            m.submit("a", "pass", 8_000)


if __name__ == "__main__":
    unittest.main()
