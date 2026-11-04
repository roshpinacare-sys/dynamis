"""End-to-end: one business job through policy → escrow → ladder → settlement →
emission → RC², the exact flow of docs/01-architecture.md §3.

This is the executable statement of the founding plan: a job paid by an entity budget,
verified independently, settled with integer math, emission strictly behind revenue.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamis_core import (BudgetEnvelope, Claim, EmissionLedger, Job, JobMachine,
                          TreasuryState, accrue, brier_score, collect_round,
                          erg_to_usds_muc, eval_payout, evaluate, floor_class,
                          law9_check, least_supported, price_verification,
                          schedule_account, usds)

WORKER = None  # built per-test; module-level PowerAccount would share state


def entity_treasury() -> TreasuryState:
    return TreasuryState(
        envelopes={"ops": BudgetEnvelope("ops", usds(3_000), "monthly")},
        daily_spent_muc=0, runway_months=8.0)


class TestOneBusinessJob(unittest.TestCase):
    def test_full_lifecycle(self):
        from dynamis_core.objects import PowerAccount
        worker = PowerAccount("pw-worker-1", stake_dyn_mu=2_500_000)

        # 1. Demand: the entity's finance agent posts a job from its ops envelope.
        value_muc = usds(500)
        d = evaluate(entity_treasury(), "post_job_escrow", value_muc, envelope="ops")
        self.assertTrue(d.allowed, d.reason)

        # 2. Verification class: priced by the ladder, Law-9-checked before funding.
        cls = floor_class(value_muc)
        vcost = price_verification(value_muc, cls)
        self.assertTrue(law9_check(vcost, value_muc)["law9_pass"])
        self.assertLessEqual(vcost, value_muc // 10, "verification must stay affordable")

        job = Job("job-e2e-001", "ent-001",
                  {"task": "process_invoices", "count": 500}, value_muc,
                  deadline_day=10, verification_class=cls, revenue_ref="env-ops-001")
        m = JobMachine(job, funded_by="env-ops-001")

        # 3. Match + execute: a worker claims and delivers with a runner receipt.
        m.fire("fund", from_="env-ops-001")
        m.fire("claim", worker="pw-worker-1")
        m.fire("deliver", claim=Claim("cl-e2e-1", job.job_id, "pw-worker-1",
                                      ("d" * 64,), "e" * 64, m.now_day))
        m.fire("start_verify")

        # 4. Verify: witness band prices the compute consumed (µ¢ per ERG).
        rnd = collect_round(1, {"w1": 29_500, "w2": 30_000, "w3": 30_500})
        compute_usds = erg_to_usds_muc(20, rnd.median_muc)  # 20 GPU-minutes ≈ $0.60
        self.assertGreater(compute_usds, 0)
        self.assertLess(compute_usds, value_muc)

        # 5. Settle: fee split, flow-gated emission strictly behind the revenue.
        m.fire("verify_pass", verifier="witness-band")
        led = EmissionLedger()
        flow = led.record_flow(job.job_id, value_muc, m.state,
                               job.revenue_ref, m.now_day)
        self.assertEqual(m.state, "SETTLED")
        self.assertEqual(m.fee_muc, usds(25))          # 5% coordination fee
        self.assertEqual(m.worker_payout_muc, usds(475))
        self.assertIsNotNone(flow)
        self.assertTrue(led.invariant_holds())

        # 6. The worker's Power Account accrues stake-weighted RC² for model calls.
        added = accrue(worker)
        self.assertGreater(added, 0)

        # 7. The chain of events re-verifies.
        self.assertTrue(m.verify_chain())

    def test_fraudulent_worker_loses(self):
        """A seeded fraud attempt at floor class is caught and pays nothing."""
        value_muc = usds(500)
        cls = floor_class(value_muc)
        job = Job("job-fraud-1", "ent-001", {"task": "process_invoices"}, value_muc,
                  10, cls, "env-ops-001")
        m = JobMachine(job, "env-ops-001")
        m.fire("fund")
        m.fire("claim", worker="pw-fraudster-1")
        m.fire("deliver", claim=Claim("cl-f-1", job.job_id, "pw-fraudster-1",
                                      ("0" * 64,), "1" * 64, m.now_day))
        m.fire("start_verify")
        m.fire("verify_fail", verifier="witness-band", reason="re-execution mismatch")
        self.assertEqual(m.state, "DISPUTED")
        m.fire("resolve_budget", arbiter="witness-band")
        self.assertEqual(m.state, "REFUNDED")
        self.assertEqual(m.worker_payout_muc, 0)   # the fraud paid nothing
        led = EmissionLedger()
        with self.assertRaises(ValueError):        # and minted nothing (Law 19)
            led.record_flow(job.job_id, value_muc, m.state, job.revenue_ref, m.now_day)

    def test_social_layer_stays_gapped_and_capped(self):
        """The army-social rail: schedules reproducible, anti-herd target chosen."""
        s = schedule_account(40, "headcorner")
        self.assertEqual(s, schedule_account(40, "headcorner"))
        target = least_supported({"p1": 12, "p2": 3, "p3": 3})
        self.assertEqual(target, "p2")

    def test_evaluator_calibrated(self):
        score = brier_score(9200, "pass", "pass")
        payout = eval_payout(usds(500), score, "pass", "pass")
        self.assertEqual(payout["fee_muc"], usds(15))
        self.assertEqual(payout["burn_muc"], 0)


if __name__ == "__main__":
    unittest.main()
