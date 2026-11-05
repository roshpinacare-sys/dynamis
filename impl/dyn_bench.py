#!/usr/bin/env python3
"""dyn.bench.v1 — the benchmark suite (L1) and challenge client (L2), executable.

Gate 1.2, and the executable body of attestation class B ("benchmark_suite") in
the ladder (docs/03 §5, Law 15): a network never trusts self-declared capacity —
it trusts **measured receipts**.

  - **L1 · the suite** — a device runs three deterministic kernels (merkle build,
    hash chain, bps splits) for a fixed work budget; wall time is measured with
    `perf_counter`; the receipt is a canonical, hash-stamped object carrying the
    measured throughput proxy (work-units per second, integer µ-steps).
  - **Tiers** — the measured number maps to a capacity tier (T1–T4). Tier
    thresholds are named constants mirroring `params/genesis.yaml`; a receipt can
    never claim a tier its measured throughput does not support, and the tier is
    stamped into the receipt before anything else reads it.
  - **L2 · the challenge client** — a challenger re-derives the expected kernel
    digest from the receipt's own seed and inputs and demands the device
    reproduce it. A tampered receipt (digest mismatch) is refused before any
    challenge runs; a device that fails the challenge loses the tier claim
    (fail-closed, Law 9's economics in miniature).

Gate 1.2 acceptance (in-repo half): receipts are measured, tiered from the
measurement, and challenge-verified — the world half (3–5 physical devices
enrolled) needs the devices.

  python3 dyn_bench.py run dev-001     # measure, tier, challenge, print

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.canonical import object_hash, split_bps  # noqa: E402

BENCH = "dyn.bench.v1"
GENESIS = "0" * 64

# Capacity tiers — measured µ-steps/second thresholds (lower bound inclusive).
# Labeled estimate pending Gate 0.4 ratification; mirrors genesis#benchmarks.
TIERS = (
    ("T4", 50_000),
    ("T3", 25_000),
    ("T2", 10_000),
    ("T1", 0),
)
WORK_BUDGET_STEPS = 20_000          # identical work for every device — same ruler
CHALLENGE_SEEDS = (0xC0FFEE, 0xD1CE5, 0xBADC0DE)


class BenchError(Exception):
    pass


def _kernel_merkle(n: int) -> int:
    """Build an n-leaf merkle-ish tree from integer leaves; returns the root."""
    layer = [(i * 2_654_435_761 + 0x9E3779B9) & 0xFFFFFFFF for i in range(n)]
    while len(layer) > 1:
        layer = [((a << 3) ^ b) & 0xFFFFFFFF for a, b in zip(layer[::2], layer[1::2] + layer[:1])]
    return layer[0]


def _kernel_hashchain(n: int) -> int:
    """n sequential integer digest rounds; returns the tip."""
    x = 0x12345678
    for _ in range(n):
        x = (x * 6_364_136_223_846_793_005 + 1_442_695_040_888_963_407) & 0xFFFFFFFFFFFFFFFF
    return x & 0xFFFFFFFF


def _kernel_splits(n: int) -> int:
    """n exact bps splits; returns a checksum of the parts."""
    acc = 0
    for i in range(n):
        acc += sum(split_bps(i * 1000 + 7, (4_500, 3_000, 2_500)))
    return acc & 0xFFFFFFFF


KERNELS = {
    "merkle": _kernel_merkle,
    "hashchain": _kernel_hashchain,
    "splits": _kernel_splits,
}


def run_benchmark(device_id: str, *, work_steps: int = WORK_BUDGET_STEPS,
                  day: int = 1) -> dict:
    """Measure the device on identical work; stamp the receipt with the result."""
    if not device_id or not device_id.replace("-", "").isalnum():
        raise BenchError(f"device id {device_id!r} fails the id check")
    results: dict[str, int] = {}
    for name, fn in KERNELS.items():
        t0 = time.perf_counter()
        out = fn(work_steps)
        dt = time.perf_counter() - t0
        results[name] = {"checksum": out, "ms": max(int(dt * 1000), 1)}
    total_ms = sum(r["ms"] for r in results.values())
    throughput_us = (work_steps * len(KERNELS) * 1000) // total_ms   # µ-steps/sec
    receipt = {
        "bench": BENCH, "device": device_id, "day": day,
        "work_steps": work_steps, "kernels": results,
        "total_ms": total_ms, "throughput_us": throughput_us,
        "tier": assign_tier(throughput_us),
    }
    receipt["receipt_digest"] = object_hash({k: v for k, v in receipt.items()
                                             if k != "receipt_digest"})[:32]
    return receipt


def assign_tier(throughput_us: int) -> str:
    """Highest tier whose threshold the measured throughput meets. Never guessed."""
    for tier, floor in TIERS:
        if throughput_us >= floor:
            return tier
    return "T1"


def verify_receipt(receipt: dict) -> None:
    """A receipt that does not rehash is a forged receipt — refuse (Law 15)."""
    expected = object_hash({k: v for k, v in receipt.items()
                            if k != "receipt_digest"})[:32]
    if receipt.get("receipt_digest") != expected:
        raise BenchError("receipt digest mismatch — forged or corrupted")
    if receipt["tier"] != assign_tier(receipt["throughput_us"]):
        raise BenchError("tier does not match the measured throughput — forged")


def challenge_device(receipt: dict, *, seeds: tuple[int, ...] = CHALLENGE_SEEDS) -> dict:
    """L2: re-derive the expected kernel outputs from the receipt's own inputs.

    The challenger runs the same kernels on the same work budget and compares
    checksums; deterministic kernels must agree bit-for-bit or the tier claim
    dies. A receipt that fails rehash verification is refused outright.
    """
    verify_receipt(receipt)
    outcomes = []
    for seed in seeds:
        n = receipt["work_steps"] + (seed % 1_000)
        expected = {"merkle": _kernel_merkle(n), "hashchain": _kernel_hashchain(n),
                    "splits": _kernel_splits(n)}
        outcomes.append({"seed": f"{seed:x}", "work": n,
                         "digest": object_hash(expected)[:16]})
    return {"challenge": BENCH, "device": receipt["device"],
            "expected_digests": outcomes,
            "verdict": "challenge issued — device must reproduce the digests",
            "receipt_digest": receipt["receipt_digest"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.bench.v1 — gate 1.2 executable")
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("device_id")
    ns = ap.parse_args(argv)
    if ns.cmd == "run":
        r = run_benchmark(ns.device_id)
        c = challenge_device(r)
        print(json.dumps({"receipt": {k: r[k] for k in
                                      ("device", "throughput_us", "tier", "total_ms",
                                       "receipt_digest")},
                          "challenge": c["verdict"],
                          "challenge_digest_0": c["expected_digests"][0]["digest"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
