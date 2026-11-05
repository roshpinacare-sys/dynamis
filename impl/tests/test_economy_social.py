"""Tests: DoA policy engine, RC², evaluator scoring, anti-herd, flow-gated emission."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamis_core.canonical import usds
from dynamis_core.policy import (BudgetEnvelope, TreasuryState,
                                 classify, evaluate, T2_THRESHOLD_MUC)
from dynamis_core.rc2 import accrue, spend, stake_factor, ACCRUAL_DIVISOR, CAP_DAYS
from dynamis_core.brier import (brier_score, bond_burn, calibration_bucket,
                                eval_payout, expected_calibration_error)
from dynamis_core.objects import PowerAccount
from dynamis_core.antiherd import (DAILY_PUBLISH_CAP, DAILY_VOTE_CAP,
                                   least_supported, mulberry32, schedule_account)
from dynamis_core.emission import EmissionLedger, SPLIT_BPS, DYN_MU_PER_USDS_MUC


def treasury(runway=12.0):
    return TreasuryState(
        envelopes={
            "ops": BudgetEnvelope("ops", usds(3_000), "monthly"),
            "growth": BudgetEnvelope("growth", usds(1_500), "monthly"),
        },
        daily_spent_muc=0, runway_months=runway)


class TestPolicy(unittest.TestCase):
    def test_t0_auto_within_envelope(self):
        d = evaluate(treasury(), "pay_vendor_bill", usds(40), envelope="ops")
        self.assertTrue(d.allowed)
        self.assertEqual(d.doa_class, "T0")
        self.assertEqual(d.requires, "none")

    def test_amount_promotes_to_t2(self):
        self.assertEqual(classify("pay_vendor_bill", T2_THRESHOLD_MUC + 1), "T2")
        d = evaluate(treasury(), "pay_vendor_bill", usds(2_001))
        self.assertFalse(d.allowed)          # capital: prepare + human approval
        self.assertEqual(d.requires, "human_approval")

    def test_t2_blocked_then_allowed_with_approval(self):
        t = treasury()
        d = evaluate(t, "spend_capital", usds(3_000))
        self.assertFalse(d.allowed)
        d2 = evaluate(t, "spend_capital", usds(3_000), human_approved=True)
        self.assertTrue(d2.allowed)

    def test_class_x_never(self):
        for kind in ("custody_client_keys", "yield_marketing", "publish_unmeasured_claim",
                     "unknown_future_kind"):
            d = evaluate(treasury(), kind, 1)
            self.assertFalse(d.allowed)
            self.assertEqual(d.doa_class, "X")

    def test_envelope_cap_hard(self):
        t = treasury()
        t.envelopes["ops"].spent_muc = usds(2_999)
        d = evaluate(t, "pay_vendor_bill", usds(2), envelope="ops")
        self.assertFalse(d.allowed)
        self.assertIn("exhausted", d.reason)

    def test_runway_breach_escalates_to_t2(self):
        d = evaluate(treasury(runway=3.0), "pay_vendor_bill", usds(40))
        self.assertEqual(d.doa_class, "T2")  # any runway breach is capital, per canon

    def test_rail_caps_fail_closed(self):
        d = evaluate(treasury(), "spend_capital", usds(30_000), human_approved=True)
        self.assertFalse(d.allowed)  # above max_single_flow — no human can wave it through

    def test_t3_needs_veto_keys(self):
        d = evaluate(treasury(), "change_doa", 0)
        self.assertFalse(d.allowed)
        self.assertEqual(d.requires, "veto_keys")
        d2 = evaluate(treasury(), "change_doa", 0, veto_keys=True)
        self.assertTrue(d2.allowed)


class TestRC2(unittest.TestCase):
    def test_accrual_capped_by_stake(self):
        pa = PowerAccount("pw-1", stake_dyn_mu=1_000_000)  # 1.0 DYN
        rate = 1_000_000 // ACCRUAL_DIVISOR
        added = accrue(pa, days=1)
        self.assertEqual(added, rate)
        for _ in range(30):
            accrue(pa)
        self.assertLessEqual(pa.erg_credits, rate * CAP_DAYS)  # 7 days of full rate

    def test_no_stake_no_credits(self):
        pa = PowerAccount("pw-broke")
        self.assertEqual(accrue(pa, days=10), 0)

    def test_spend_denies_by_default(self):
        pa = PowerAccount("pw-1", stake_dyn_mu=1_000_000)
        with self.assertRaises(ValueError):
            spend(pa, 1)
        accrue(pa)
        spend(pa, 1_000_000 // ACCRUAL_DIVISOR)
        with self.assertRaises(ValueError):
            spend(pa, 1)  # empty again — deny

    def test_stake_factor_integer_sqrt(self):
        pa = PowerAccount("pw-1", stake_dyn_mu=9_000_000)
        self.assertEqual(stake_factor(pa), 3)
        self.assertEqual(stake_factor(PowerAccount("pw-0")), 0)


class TestBrier(unittest.TestCase):
    def test_perfect_and_awful(self):
        self.assertEqual(brier_score(9000, "pass", "pass"), 100)      # confident & right
        self.assertEqual(brier_score(9000, "pass", "fail"), 8100)     # confidently wrong
        self.assertEqual(brier_score(5000, "pass", "pass"), 2500)     # coin flip

    def test_bond_burn_capped_and_proportional(self):
        self.assertEqual(bond_burn(1000_00, 0), 0)
        self.assertEqual(bond_burn(1000_00, 10000), 400_00)           # K = 0.4
        self.assertLessEqual(bond_burn(1000_00, 10000), 1000_00)

    def test_eval_payout_symmetry(self):
        good = eval_payout(1000_00, 100, "pass", "pass")
        bad = eval_payout(1000_00, 8100, "pass", "fail")
        self.assertEqual(good["fee_muc"], 30_00)
        self.assertEqual(good["burn_muc"], 0)
        self.assertEqual(bad["burn_muc"], 324_00)

    def test_calibration_bucketing_and_ece(self):
        self.assertEqual(calibration_bucket(9550), "90-100")
        ece = expected_calibration_error({"90-100": (100, 5), "50-60": (2500, 5)})
        self.assertEqual(ece, 1300)


class TestAntiHerd(unittest.TestCase):
    def test_deterministic_per_day_account(self):
        a = schedule_account(20, "headcorner")
        b = schedule_account(20, "headcorner")
        self.assertEqual(a, b)                     # reproducible post-hoc (Law 14)
        c = schedule_account(21, "headcorner")
        self.assertNotEqual(a["actions"], c["actions"])

    def test_caps_and_gaps_enforced(self):
        for day in range(1, 30):
            for acct in ("headcorner", "woq", "lsa", "siq"):
                s = schedule_account(day, acct)
                kinds = [a["kind"] for a in s["actions"]]
                self.assertLessEqual(kinds.count("publish"), DAILY_PUBLISH_CAP)
                self.assertLessEqual(kinds.count("vote"), DAILY_VOTE_CAP)
                self.assertLessEqual(kinds.count("reply"), 2)
                slots = sorted(a["slot"] for a in s["actions"])
                for prev, cur in zip(slots, slots[1:]):
                    self.assertGreaterEqual(cur - prev, 3)  # MIN_GAP_SLOTS

    def test_least_supported_anti_herd_target(self):
        self.assertEqual(least_supported({"a": 10, "b": 2, "c": 2}), "b")
        self.assertEqual(least_supported({"a": 2, "b": 2}), "a")   # deterministic tie-break

    def test_prng_matches_reference_vector(self):
        r = mulberry32(0)
        # Cross-verified bit-exact against the reference JS implementation (Node).
        self.assertEqual(next(r), 1144304738)


class TestEmission(unittest.TestCase):
    def test_split_sums_to_ten_thousand(self):
        self.assertEqual(sum(SPLIT_BPS.values()), 10000)

    def test_no_flow_no_emission_law19(self):
        led = EmissionLedger()
        with self.assertRaises(ValueError):
            led.record_flow("job-x-1", usds(100), "FUNDED", "env-ops-001", 1)
        self.assertEqual(led.cumulative_emitted_dyn_mu, 0)

    def test_settled_flow_emits_exact_split(self):
        led = EmissionLedger()
        flow = led.record_flow("job-x-1", usds(1000), "SETTLED", "env-ops-001", 5)
        self.assertEqual(flow["emitted_dyn_mu"], usds(1000) * DYN_MU_PER_USDS_MUC)
        self.assertEqual(sum(flow["split"].values()), flow["emitted_dyn_mu"])
        self.assertTrue(led.invariant_holds())

    def test_no_double_emission(self):
        led = EmissionLedger()
        led.record_flow("job-x-1", usds(100), "SETTLED", "env-ops-001", 1)
        with self.assertRaises(ValueError):
            led.record_flow("job-x-1", usds(100), "SETTLED", "env-ops-001", 2)

    def test_invariant_is_mathematical_not_vibes(self):
        led = EmissionLedger()
        for i in range(10):
            led.record_flow(f"job-x-{i}", usds(500) + i, "SETTLED", "env-ops-001", i + 1)
        self.assertEqual(
            led.cumulative_emitted_dyn_mu,
            led.cumulative_revenue_usds_muc * DYN_MU_PER_USDS_MUC)


if __name__ == "__main__":
    unittest.main()
