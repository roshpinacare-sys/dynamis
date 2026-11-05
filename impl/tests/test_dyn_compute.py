"""Tests: dyn.compute.v1 — the shared pool (docs/03 §7, specs/benchmarks.md).

The invariants that matter: no device without a receipt that rehashes (Law 15),
no allocation without an accepted witness price round, the scheduler picks the
smallest sufficient tier and the least-used device (best-fit + anti-herd,
Laws 13–14), settlement is exact integer µ¢ with the kernel coordination fee,
settlement mints nothing (Law 19), refusals are recorded, and the kill switch
refuses every mutation.
"""
import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dynamis_core.escrow import COORDINATION_FEE_BPS  # noqa: E402
from dynamis_core.pricefeed import collect_round  # noqa: E402
from dyn_bench import assign_tier, run_benchmark  # noqa: E402
from dyn_compute import (DEVICE_DAILY_ERG_MILLI, MAX_JOB_ERG_MILLI,
                         ComputeError, Pool, kill, revive)
from dyn_compute import _receipt as synthetic_receipt  # noqa: E402


def price_round(day: int = 11, median: int = 30_000) -> object:
    return collect_round(day, {"w1": median - 2_000, "w2": median,
                               "w3": median + 2_000, "w4": median})


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.pool = Pool()
        self.day = 11

    def test_real_benchmark_receipt_registers(self):
        receipt = run_benchmark("dev-real-1")     # measured on this machine
        tier = receipt["tier"]
        self.pool.register_device("dev-real-1", receipt, day=self.day)
        dev = self.pool.devices["dev-real-1"]
        self.assertEqual(dev["tier"], tier)
        self.assertEqual(tier, assign_tier(receipt["throughput_us"]))

    def test_tampered_receipt_refused_and_recorded(self):
        receipt = synthetic_receipt("dev-fake-1", 30_000)
        receipt["throughput_us"] = 999_999        # edit after stamping
        with self.assertRaises(ComputeError) as ctx:
            self.pool.register_device("dev-fake-1", receipt, day=self.day)
        self.assertIn("REFUSED-NO-RECEIPT", str(ctx.exception))
        self.assertEqual(len(self.pool.ledger.refusals("REFUSED-NO-RECEIPT")), 1)

    def test_duplicate_device_refused(self):
        receipt = synthetic_receipt("dev-1", 30_000)
        self.pool.register_device("dev-1", receipt, day=self.day)
        with self.assertRaises(ComputeError):
            self.pool.register_device("dev-1", receipt, day=self.day)

    def test_unknown_class_floor_refused(self):
        with self.assertRaises(ComputeError):
            self.pool.register_device("dev-1", synthetic_receipt("dev-1", 30_000),
                                      day=self.day, class_floor="Z")


class TestPricing(unittest.TestCase):
    def setUp(self):
        self.pool = Pool()
        self.day = 11

    def test_no_price_no_allocation(self):
        self.pool.register_device("dev-1", synthetic_receipt("dev-1", 30_000),
                                  day=self.day)
        self.pool.post_job("job-1", "ent-001", day=self.day, erg_milli=1_000)
        with self.assertRaises(ComputeError) as ctx:
            self.pool.allocate(day=self.day)
        self.assertIn("REFUSED-NO-PRICE", str(ctx.exception))

    def test_price_round_is_stored_and_ledgered(self):
        rnd = price_round()
        median = self.pool.set_price_round(rnd, day=self.day)
        self.assertEqual(median, rnd.median_muc)
        self.assertEqual(self.pool.ledger.entries[-1]["kind"], "price")


class TestScheduler(unittest.TestCase):
    """The intelligent allocator: eligible, best-fit, fair, deterministic."""

    def setUp(self):
        self.pool = Pool()
        self.day = 11
        self.pool.register_device("dev-gpu", synthetic_receipt("dev-gpu", 30_000),
                                  day=self.day)       # T3
        self.pool.register_device("dev-cpu", synthetic_receipt("dev-cpu", 6_000),
                                  day=self.day)       # T1
        self.pool.set_price_round(price_round(), day=self.day)

    def test_best_fit_picks_smallest_sufficient_tier(self):
        self.pool.post_job("job-small", "ent-001", day=self.day,
                           erg_milli=1_000, tier_min="T1")
        out = self.pool.allocate(day=self.day)
        self.assertEqual(out["allocated"][0]["device"], "dev-cpu")

    def test_tier_floor_keeps_big_jobs_on_big_devices(self):
        self.pool.post_job("job-big", "ent-001", day=self.day,
                           erg_milli=2_400, tier_min="T3")
        out = self.pool.allocate(day=self.day)
        self.assertEqual(out["allocated"][0]["device"], "dev-gpu")

    def test_unreachable_tier_is_refused_and_recorded(self):
        self.pool.post_job("job-huge", "ent-001", day=self.day,
                           erg_milli=2_400, tier_min="T4")
        out = self.pool.allocate(day=self.day)
        self.assertEqual(out["queued"][0]["reason"], "REFUSED-TIER")
        self.assertEqual(len(self.pool.ledger.refusals("REFUSED-TIER")), 1)

    def test_class_floor_refused_when_no_device_qualifies(self):
        self.pool.post_job("job-zk", "ent-001", day=self.day,
                           erg_milli=1_000, tier_min="T1", class_min="E")
        out = self.pool.allocate(day=self.day)
        self.assertEqual(out["queued"][0]["reason"], "REFUSED-CLASS")

    def test_equal_tiers_rotate_by_fair_share(self):
        self.pool.register_device("dev-gpu2",
                                  synthetic_receipt("dev-gpu2", 30_000),
                                  day=self.day)      # same tier as dev-gpu
        self.pool.post_job("job-1", "ent-001", day=self.day, erg_milli=1_000,
                           tier_min="T3")
        self.pool.post_job("job-2", "ent-001", day=self.day, erg_milli=1_000,
                           tier_min="T3")
        out = self.pool.allocate(day=self.day)
        devices = sorted(a["device"] for a in out["allocated"])
        self.assertEqual(devices, ["dev-gpu", "dev-gpu2"])

    def test_daily_capacity_is_enforced(self):
        """Twelve max-size jobs exactly fill the daily metering cap; the
        thirteenth waits with REFUSED-CAPACITY."""
        pool = Pool()
        pool.register_device("dev-cpu", synthetic_receipt("dev-cpu", 6_000),
                             day=self.day)
        pool.set_price_round(price_round(), day=self.day)
        for i in range(DEVICE_DAILY_ERG_MILLI // MAX_JOB_ERG_MILLI):
            pool.post_job(f"job-{i:02d}", "ent-001", day=self.day,
                          erg_milli=MAX_JOB_ERG_MILLI, tier_min="T1")
        pool.post_job("job-over", "ent-001", day=self.day, erg_milli=1,
                      tier_min="T1")
        out = pool.allocate(day=self.day)
        self.assertEqual(len(out["allocated"]),
                         DEVICE_DAILY_ERG_MILLI // MAX_JOB_ERG_MILLI)
        reasons = {q["job_id"]: q["reason"] for q in out["queued"]}
        self.assertEqual(reasons["job-over"], "REFUSED-CAPACITY")

    def test_oversize_job_refused_at_the_door(self):
        with self.assertRaises(ComputeError) as ctx:
            self.pool.post_job("job-x", "ent-001", day=self.day,
                               erg_milli=MAX_JOB_ERG_MILLI + 1)
        self.assertIn("REFUSED-OVERSIZE", str(ctx.exception))
        self.assertEqual(len(self.pool.ledger.refusals("REFUSED-OVERSIZE")), 1)

    def test_allocation_is_deterministic(self):
        self.pool.post_job("job-1", "ent-001", day=self.day, erg_milli=1_000,
                           tier_min="T1")
        first = self.pool.allocate(day=self.day)
        self.pool2 = Pool()
        self.pool2.register_device("dev-gpu",
                                   synthetic_receipt("dev-gpu", 30_000),
                                   day=self.day)
        self.pool2.register_device("dev-cpu",
                                   synthetic_receipt("dev-cpu", 6_000),
                                   day=self.day)
        self.pool2.set_price_round(price_round(), day=self.day)
        self.pool2.post_job("job-1", "ent-001", day=self.day, erg_milli=1_000,
                            tier_min="T1")
        second = self.pool2.allocate(day=self.day)
        self.assertEqual(first["allocated"], second["allocated"])


class TestMeteringAndSettlement(unittest.TestCase):
    def setUp(self):
        self.pool = Pool()
        self.day = 11
        self.pool.register_device("dev-gpu", synthetic_receipt("dev-gpu", 30_000),
                                  day=self.day)
        self.median = self.pool.set_price_round(price_round(), day=self.day)
        self.pool.post_job("job-1", "ent-001", day=self.day, erg_milli=2_400,
                           tier_min="T2")
        self.pool.allocate(day=self.day)

    def test_settlement_is_exact_integer_money(self):
        out = self.pool.settle("job-1", day=self.day)
        cost = 2_400 * self.median                 # erg_to_usds_muc, exact
        fee = cost * COORDINATION_FEE_BPS // 10_000
        self.assertEqual(out["cost_muc"], cost)
        self.assertEqual(out["fee_muc"], fee)
        self.assertEqual(out["payout_muc"], cost - fee)
        self.assertEqual(out["device"], "dev-gpu")

    def test_settlement_mints_nothing_law19(self):
        out = self.pool.settle("job-1", day=self.day)
        self.assertEqual(out["cost_muc"], out["fee_muc"] + out["payout_muc"])
        kinds = [e["kind"] for e in self.pool.ledger.entries]
        self.assertNotIn("emit", kinds)            # emission is not the pool's

    def test_unallocated_job_cannot_settle(self):
        self.pool.post_job("job-2", "ent-001", day=self.day, erg_milli=100)
        with self.assertRaises(ComputeError) as ctx:
            self.pool.settle("job-2", day=self.day)
        self.assertIn("REFUSED-STATE", str(ctx.exception))

    def test_meter_event_precedes_settle_event(self):
        self.pool.settle("job-1", day=self.day)
        kinds = [e["kind"] for e in self.pool.ledger.entries]
        self.assertLess(kinds.index("meter"), kinds.index("settle"))


class TestKillSwitchAndLedger(unittest.TestCase):
    def test_kill_switch_refuses_every_mutation(self):
        pool = Pool()
        pool.register_device("dev-1", synthetic_receipt("dev-1", 30_000), day=11)
        kill()
        try:
            with self.assertRaises(ComputeError) as ctx:
                pool.register_device("dev-2",
                                     synthetic_receipt("dev-2", 30_000), day=11)
            self.assertIn("REFUSED-KILL", str(ctx.exception))
            with self.assertRaises(ComputeError):
                pool.post_job("job-1", "ent-001", day=11, erg_milli=1_000)
        finally:
            revive()

    def test_chain_verifies_and_tampering_breaks_it(self):
        pool = Pool()
        pool.register_device("dev-1", synthetic_receipt("dev-1", 30_000), day=11)
        pool.set_price_round(price_round(), day=11)
        pool.post_job("job-1", "ent-001", day=11, erg_milli=1_000, tier_min="T1")
        pool.allocate(day=11)
        pool.settle("job-1", day=11)
        self.assertTrue(pool.ledger.verify_chain()["ok"])
        pool.ledger.entries[-1]["body"]["payout_muc"] = 10 ** 12
        self.assertFalse(pool.ledger.verify_chain()["ok"])


if __name__ == "__main__":
    unittest.main()
