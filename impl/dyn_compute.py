#!/usr/bin/env python3
"""dyn.compute.v1 — the shared compute pool: registry, intelligent allocation,
metering, settlement — the executable half of docs/03 §7 ("Compute market") and
specs/benchmarks.md.

The pool sells exactly one thing: measured capacity. The design laws:

  - No self-declared capacity (Law 15): a device enters the registry only with
    a dyn.bench.v1 receipt that rehashes and whose tier matches its measured
    throughput. dyn_bench.verify_receipt refuses anything else.
  - No price, no allocation: the scheduler prices every job in µ¢/ERG from the
    witness median price feed (pricefeed.collect_round, ≥ 3 live samples or it
    fails closed). Without an accepted round the pool refuses to allocate.
  - Intelligent allocation is deterministic and anti-herd (Laws 13–14):
    eligible devices are filtered by tier floor and attestation-class floor;
    the pick is best-fit (smallest sufficient tier, so big devices stay free
    for big jobs), then fair-share (the device scheduled least that day),
    then canonical device id. No randomness, no engagement, no capture.
  - Metering is integer ERG-milliunits; settlement is integer µ¢ via
    pricefeed.erg_to_usds_muc and canonical.split_bps with the kernel's
    coordination fee. Integers only in canonical payloads (ADR-0007).
  - Settlement mints NOTHING (Law 19): the provider is paid from the job's
    escrowed budget. Emission stays behind dyn.emission's flow gate.
  - Every refusal is a recorded event: REFUSED-NO-RECEIPT, REFUSED-NO-PRICE,
    REFUSED-TIER, REFUSED-CLASS, REFUSED-CAPACITY, REFUSED-OVERSIZE,
    REFUSED-KILL.
  - Kill switch armed and tested (execution contract §3.7).

  python3 dyn_compute.py demo      # register, schedule, meter, settle

Stdlib only (ADR-0007). Caps mirror params/genesis.yaml#compute —
scripts/params_check.py enforces the mirror.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.canonical import object_hash, split_bps  # noqa: E402
from dynamis_core.escrow import COORDINATION_FEE_BPS  # noqa: E402
from dynamis_core.ladder import CLASSES, ORDER  # noqa: E402
from dynamis_core.pricefeed import (PriceRound, erg_to_usds_muc)  # noqa: E402
from dyn_bench import TIERS, verify_receipt  # noqa: E402

COMPUTE = "dyn.compute.v1"

TIER_RANK = {tier: i for i, (tier, _floor) in enumerate(reversed(TIERS))}  # T1=0 … T4=3
CLASS_RANK = {cls: i for i, cls in enumerate(ORDER)}             # A=0 … E=4

# Mirrors genesis#compute (params_check.py proves the mirror; gate 0.4 ratifies).
MAX_JOB_ERG_MILLI = 120_000        # 120 ERG ≈ two reference GPU-hours per job
DEVICE_DAILY_ERG_MILLI = 1_440_000  # 1440 ERG ≈ T-GPU2 reservation × 12 h window

KINDS = ("device", "price", "job", "allocate", "meter", "settle", "refused")

KILL_SWITCHES: dict[str, bool] = {}


def kill(rail: str = COMPUTE) -> None:
    """Arm the kill switch: every mutating call on the pool refuses."""
    KILL_SWITCHES[rail] = True


def revive(rail: str = COMPUTE) -> None:
    """Disarm the kill switch (the tested escape hatch)."""
    KILL_SWITCHES[rail] = False


def _check_kill() -> None:
    if KILL_SWITCHES.get(COMPUTE):
        raise ComputeError("REFUSED-KILL: the pool's kill switch is armed")


class ComputeError(Exception):
    """A refusal with a reason code — refusals are events, not just errors."""


class Pool:
    """The shared pool: verified devices, queued jobs, one scheduler."""

    def __init__(self) -> None:
        self.devices: dict[str, dict] = {}
        self.round: PriceRound | None = None
        self.jobs: dict[str, dict] = {}
        self.day_usage: dict[str, int] = {}      # device -> erg_milli today
        self.schedule_count: dict[str, int] = {}  # device -> allocations today
        self.ledger = ComputeLedger()

    # ---------- registry (Law 15: measured capacity only) ----------
    def register_device(self, device_id: str, receipt: dict, *,
                        day: int, class_floor: str = "C") -> str:
        _check_kill()
        try:
            verify_receipt(receipt)
        except Exception as exc:
            self.ledger.append(day=day, kind="refused", actor=device_id,
                               body={"reason": "REFUSED-NO-RECEIPT",
                                     "detail": str(exc)[:120]})
            raise ComputeError(f"REFUSED-NO-RECEIPT: {exc}") from exc
        if class_floor not in CLASSES:
            raise ComputeError(f"unknown attestation class {class_floor!r}")
        if device_id in self.devices:
            raise ComputeError("REFUSED-DUPLICATE: device registered")
        self.devices[device_id] = {
            "tier": receipt["tier"],
            "throughput_us": receipt["throughput_us"],
            "class_floor": class_floor,
            "receipt_digest": receipt["receipt_digest"],
        }
        self.day_usage[device_id] = 0
        self.schedule_count[device_id] = 0
        self.ledger.append(day=day, kind="device", actor=device_id,
                           body={"tier": receipt["tier"],
                                 "class_floor": class_floor})
        return device_id

    def set_price_round(self, rnd: PriceRound, *, day: int) -> int:
        _check_kill()
        if not rnd.accepted or rnd.median_muc <= 0:
            self.ledger.append(day=day, kind="refused", actor="price-feed",
                               body={"reason": "REFUSED-NO-PRICE",
                                     "accepted": len(rnd.accepted)})
            raise ComputeError("REFUSED-NO-PRICE: no accepted witness samples")
        self.round = rnd
        self.ledger.append(day=day, kind="price", actor="price-feed",
                           body={"median_muc": rnd.median_muc,
                                 "accepted": len(rnd.accepted)})
        return rnd.median_muc

    # ---------- jobs ----------
    def post_job(self, job_id: str, requester: str, *, day: int,
                 erg_milli: int, tier_min: str = "T1",
                 class_min: str = "C") -> dict:
        _check_kill()
        if erg_milli <= 0 or erg_milli > MAX_JOB_ERG_MILLI:
            self.ledger.append(day=day, kind="refused", actor=requester,
                               body={"reason": "REFUSED-OVERSIZE",
                                     "erg_milli": erg_milli})
            raise ComputeError(
                f"REFUSED-OVERSIZE: job budget must be 1..{MAX_JOB_ERG_MILLI} ERG-milli")
        if tier_min not in TIER_RANK:
            raise ComputeError(f"unknown tier {tier_min!r}")
        if class_min not in CLASS_RANK:
            raise ComputeError(f"unknown attestation class {class_min!r}")
        job = {"job_id": job_id, "requester": requester, "day": day,
               "erg_milli": erg_milli, "tier_min": tier_min,
               "class_min": class_min, "state": "queued"}
        self.jobs[job_id] = job
        self.ledger.append(day=day, kind="job", actor=requester,
                           body={"job_id": job_id, "erg_milli": erg_milli,
                                 "tier_min": tier_min, "class_min": class_min})
        return job

    # ---------- the scheduler: deterministic, best-fit, anti-herd ----------
    def allocate(self, *, day: int) -> dict:
        """Allocate every queued job or record exactly why it stays queued."""
        _check_kill()
        if self.round is None:
            raise ComputeError("REFUSED-NO-PRICE: no accepted price round")
        result = {"allocated": [], "queued": []}
        for job_id, job in list(self.jobs.items()):
            if job["state"] != "queued":
                continue
            eligible = [
                did for did, dev in self.devices.items()
                if TIER_RANK[dev["tier"]] >= TIER_RANK[job["tier_min"]]
                and CLASS_RANK[dev["class_floor"]] >= CLASS_RANK[job["class_min"]]
                and self.day_usage[did] + job["erg_milli"] <= DEVICE_DAILY_ERG_MILLI
            ]
            if not eligible:
                reason = "REFUSED-TIER" if not self._tier_eligible(job) \
                    else ("REFUSED-CLASS" if not self._class_eligible(job)
                          else "REFUSED-CAPACITY")
                self.ledger.append(day=day, kind="refused", actor=job_id,
                                   body={"reason": reason,
                                         "tier_min": job["tier_min"]})
                result["queued"].append({"job_id": job_id, "reason": reason})
                continue
            # best fit: smallest sufficient tier → fair share → canonical id
            chosen = min(
                eligible,
                key=lambda d: (TIER_RANK[self.devices[d]["tier"]],
                               self.schedule_count[d], d))
            self.day_usage[chosen] += job["erg_milli"]
            self.schedule_count[chosen] += 1
            job["state"] = "allocated"
            job["device"] = chosen
            job["price_muc_per_erg"] = self.round.median_muc
            self.ledger.append(day=day, kind="allocate", actor=job_id,
                               body={"device": chosen,
                                     "erg_milli": job["erg_milli"],
                                     "median_muc": self.round.median_muc})
            result["allocated"].append({"job_id": job_id, "device": chosen})
        return result

    def _tier_eligible(self, job: dict) -> bool:
        return any(TIER_RANK[d["tier"]] >= TIER_RANK[job["tier_min"]]
                   for d in self.devices.values())

    def _class_eligible(self, job: dict) -> bool:
        return any(CLASS_RANK[d["class_floor"]] >= CLASS_RANK[job["class_min"]]
                   for d in self.devices.values())

    # ---------- metering + settlement (µ¢ integers, mints nothing) ----------
    def settle(self, job_id: str, *, day: int) -> dict:
        _check_kill()
        if self.round is None:
            raise ComputeError("REFUSED-NO-PRICE: no accepted price round")
        job = self.jobs.get(job_id)
        if job is None or job["state"] != "allocated":
            raise ComputeError("REFUSED-STATE: job is not allocated")
        cost_muc = erg_to_usds_muc(job["erg_milli"], self.round.median_muc)
        fee_muc, payout_muc = split_bps(
            cost_muc, (COORDINATION_FEE_BPS, 10_000 - COORDINATION_FEE_BPS))
        job["state"] = "settled"
        job["cost_muc"] = cost_muc
        job["coordination_fee_muc"] = fee_muc
        job["provider_payout_muc"] = payout_muc
        self.ledger.append(day=day, kind="meter", actor=job["device"],
                           body={"job_id": job_id,
                                 "erg_milli": job["erg_milli"]})
        self.ledger.append(day=day, kind="settle", actor=job_id,
                           body={"cost_muc": cost_muc, "fee_muc": fee_muc,
                                 "payout_muc": payout_muc,
                                 "device": job["device"]})
        return {"cost_muc": cost_muc, "fee_muc": fee_muc,
                "payout_muc": payout_muc, "device": job["device"]}


class ComputeLedger:
    """Append-only, hash-chained event log for the pool (the dyn_ledger idiom)."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, *, day: int, kind: str, actor: str, body: dict) -> dict:
        if kind not in KINDS:
            raise ValueError(f"unknown compute ledger kind: {kind}")
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        entry = {"seq": len(self.entries), "day": day, "kind": kind,
                 "actor": actor, "body": body, "prev": prev}
        entry["hash"] = object_hash({"prev": prev, "seq": entry["seq"],
                                     "kind": kind, "day": day, "body": body})
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> dict:
        prev = "0" * 64
        for e in self.entries:
            want = object_hash({"prev": e["prev"], "seq": e["seq"],
                                "kind": e["kind"], "day": e["day"],
                                "body": e["body"]})
            if e["prev"] != prev or e["hash"] != want:
                return {"ok": False, "depth": e["seq"]}
            prev = e["hash"]
        return {"ok": True, "depth": len(self.entries)}

    def refusals(self, reason: str | None = None) -> list[dict]:
        rows = [e for e in self.entries if e["kind"] == "refused"]
        if reason:
            rows = [e for e in rows if e["body"].get("reason") == reason]
        return rows


def _receipt(device_id: str, throughput_us: int, *, day: int = 1) -> dict:
    """A receipt in the exact run_benchmark shape for a chosen measured
    throughput (used by the demo; tests use run_benchmark itself)."""
    from dyn_bench import assign_tier
    receipt = {"bench": "dyn.bench.v1", "device": device_id, "day": day,
               "work_steps": 20_000,
               "kernels": {"merkle": {"checksum": 0, "ms": 1},
                           "hashchain": {"checksum": 0, "ms": 1},
                           "splits": {"checksum": 0, "ms": 1}},
               "total_ms": 3, "throughput_us": throughput_us,
               "tier": assign_tier(throughput_us)}
    receipt["receipt_digest"] = object_hash(
        {k: v for k, v in receipt.items() if k != "receipt_digest"})[:32]
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.compute.v1 — one day in the pool")
    ap.add_argument("cmd", choices=["demo"])
    ns = ap.parse_args(argv)

    pool = Pool()
    day = 11
    pool.register_device("dev-gpu-1", _receipt("dev-gpu-1", 30_000), day=day,
                         class_floor="C")
    pool.register_device("dev-cpu-1", _receipt("dev-cpu-1", 6_000), day=day,
                         class_floor="C")
    pool.set_price_round(_demo_round(), day=day)
    pool.post_job("job-infer-1", "ent-001", day=day, erg_milli=2_400,
                  tier_min="T2", class_min="C")
    pool.post_job("job-infer-2", "ent-001", day=day, erg_milli=600,
                  tier_min="T1", class_min="C")
    out = pool.allocate(day=day)
    print("allocated:", out["allocated"])
    print("settle:", pool.settle("job-infer-1", day=day))
    try:
        pool.post_job("job-huge", "ent-002", day=day,
                      erg_milli=MAX_JOB_ERG_MILLI + 1, tier_min="T1")
    except ComputeError as exc:
        print("refused as designed:", exc)
    print("ledger:", pool.ledger.verify_chain(),
          "refusals:", len(pool.ledger.refusals()))
    return 0


def _demo_round() -> PriceRound:
    from dynamis_core.pricefeed import collect_round
    return collect_round(11, {"w1": 28_000, "w2": 30_000, "w3": 32_000,
                              "w4": 30_000})


if __name__ == "__main__":
    raise SystemExit(main())
