"""Tests: attestation ladder + Law 9 fraud economics, witness price feed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamis_core.canonical import usds
from dynamis_core.ladder import (expected_fraud_profit_muc, floor_class,
                                 law9_check, price_verification, sample_for_reexecution)
from dynamis_core.pricefeed import collect_round, erg_to_usds_muc


class TestLadder(unittest.TestCase):
    def test_prices_monotonic_in_class(self):
        v = usds(1000)
        prices = [price_verification(v, c) for c in ("A", "B", "C", "D", "E")]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(prices[0], usds(2))    # class A: 20 bps
        self.assertEqual(prices[2], usds(40))   # class C: 400 bps

    def test_class_a_leaves_fraud_profitable_law9(self):
        v = usds(1000)
        self.assertGreater(expected_fraud_profit_muc(v, "A"), 0,
                           "class A alone must be an unprofitable fraud target — "
                           "that is why money jobs never run at class A")
        self.assertLess(expected_fraud_profit_muc(v, "C"), 0)

    def test_floor_class_escalates_with_value(self):
        f_small = floor_class(usds(1))
        self.assertIn(f_small, ("B", "C"))
        # a $10M job against a $1,000 bonded pool must be refused outright (Law 9)
        with self.assertRaises(ValueError):
            floor_class(usds(10_000_000), bond_cap_muc=usds(1000))

    def test_law9_check_pass_and_fail(self):
        v = usds(1000)
        needed = price_verification(v, floor_class(v))
        ok = law9_check(needed, v)
        self.assertTrue(ok["law9_pass"])
        self.assertEqual(ok["max_profitable_fraud_muc"], 0)
        bad = law9_check(needed // 2, v)        # can only afford class A
        self.assertFalse(bad["law9_pass"])
        self.assertEqual(bad["max_profitable_fraud_muc"],
                         expected_fraud_profit_muc(v, "A"))
        broke = law9_check(0, v)
        self.assertFalse(broke["law9_pass"])
        self.assertEqual(broke["max_profitable_fraud_muc"], v)  # unverified: all stealable

    def test_reexecution_sample_deterministic_and_covers(self):
        s1 = sample_for_reexecution(100, seed=7)
        s2 = sample_for_reexecution(100, seed=7)
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 10)  # ~10% of claims
        self.assertTrue(all(0 <= i < 100 for i in s1))
        self.assertEqual(sample_for_reexecution(5, seed=1), sample_for_reexecution(5, seed=1))
        self.assertEqual(sample_for_reexecution(0, seed=1), [])


class TestPriceFeed(unittest.TestCase):
    def test_median_and_outlier_flagging(self):
        # µ¢ per ERG; $1.80/GPU-hour ≈ 30_000 µ¢ per GPU-minute
        rnd = collect_round(1, {"w1": 30_000, "w2": 31_000, "w3": 30_500,
                                "w4": 250_000, "w5": 29_800})
        self.assertEqual(rnd.median_muc, 30_500)
        self.assertIn("w4", rnd.outliers)          # far outside ±25%
        self.assertEqual(sorted(rnd.accepted), ["w1", "w2", "w3", "w5"])
        self.assertGreater(rnd.outliers["w4"], 2500)

    def test_even_count_median_integer(self):
        rnd = collect_round(1, {"a": 100, "b": 101, "c": 103, "d": 105})
        self.assertEqual(rnd.median_muc, 102)      # (101+103)//2, integer only

    def test_fails_closed_on_too_few_samples(self):
        with self.assertRaises(ValueError):
            collect_round(1, {"w1": 150, "w2": 151})

    def test_band_tolerates_honest_spread(self):
        rnd = collect_round(1, {"w1": 30_000, "w2": 33_000, "w3": 29_500})
        self.assertEqual(rnd.outliers, {})         # ±25% band absorbs honest spread

    def test_erg_conversion(self):
        # 1 ERG = 1 GPU-minute; 60 ERG = one hour at $1.80/hour
        self.assertEqual(erg_to_usds_muc(60, 30_000), usds(1) + usds(0) + 800_000)
        self.assertEqual(erg_to_usds_muc(1, 30_000), 30_000)
        with self.assertRaises(ValueError):
            erg_to_usds_muc(10, 0)


if __name__ == "__main__":
    unittest.main()
