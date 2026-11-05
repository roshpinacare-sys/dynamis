"""The attestation ladder (docs/03-protocol.md §5) and Law 9 fraud economics.

Classes A–E price verification effort; Law 9 sets the floor: the verification band's
budget must always exceed the maximum profitable fraud it can catch. This module makes
that law executable: `floor_class()` returns the cheapest class whose expected fraud
profit is negative; `law9_check()` grades any proposed budget against that floor.

Fraud model (estimate, replaced by measured values at Gate 2.3):
  expected_profit = value × (1 − p_caught) − collectable_penalty × p_caught
  collectable_penalty = min(value × penalty_multiple, bond_cap)  — you cannot collect
  more bond than exists; bond_cap models the network's bonded stake ceiling.
"""
from __future__ import annotations

from dataclasses import dataclass

from .canonical import bps_of, usds

DEFAULT_BOND_CAP_MUC = usds(100_000)   # network bonded-pool ceiling per job (estimate)


@dataclass(frozen=True)
class LadderClass:
    name: str
    mechanism: str
    cost_bps: int              # verification cost as bps of job value (estimate)
    p_caught_bps: int          # probability fraud is caught (estimate)
    penalty_multiple: int      # slashing multiple of gained fraud value


CLASSES: dict[str, LadderClass] = {
    "A": LadderClass("deterministic_checks", "schema, tests, hashes",           20,  3000, 1),
    "B": LadderClass("benchmark_suite",      "runner-kit benchmarks on claim", 100,  7000, 2),
    "C": LadderClass("sampled_reexecution",  "default for money jobs",          400,  9500, 3),
    "D": LadderClass("tee_attestation",      "NVIDIA CC proof of model-on-GPU", 500,  9900, 4),
    "E": LadderClass("zkml_proof",           "crypto root-of-trust, small models", 1500, 9999, 5),
}
ORDER = ("A", "B", "C", "D", "E")


def price_verification(job_value_muc: int, cls: str) -> int:
    """Verification fee for a job of `job_value_muc`, charged against its escrow."""
    if cls not in CLASSES:
        raise ValueError(f"unknown ladder class {cls!r}")
    return bps_of(job_value_muc, CLASSES[cls].cost_bps)


def expected_fraud_profit_muc(job_value_muc: int, cls: str,
                              bond_cap_muc: int = DEFAULT_BOND_CAP_MUC) -> int:
    """Expected profit of a fully fraudulent claim, µ¢. Negative is the design goal."""
    if cls not in CLASSES:
        raise ValueError(f"unknown ladder class {cls!r}")
    c = CLASSES[cls]
    caught = bps_of(job_value_muc, c.p_caught_bps)
    penalty = min(job_value_muc * c.penalty_multiple, bond_cap_muc)
    return job_value_muc - caught - bps_of(penalty, c.p_caught_bps)


def floor_class(job_value_muc: int, bond_cap_muc: int = DEFAULT_BOND_CAP_MUC) -> str:
    """Cheapest class whose expected fraud profit is strictly negative (Law 9)."""
    for cls in ORDER:
        if expected_fraud_profit_muc(job_value_muc, cls, bond_cap_muc) < 0:
            return cls
    raise ValueError(f"no ladder class covers value {job_value_muc} µ¢ under bond cap "
                     f"{bond_cap_muc} µ¢ — raise bonds or refuse the job (Law 9)")


def law9_check(verification_budget_muc: int, job_value_muc: int,
               bond_cap_muc: int = DEFAULT_BOND_CAP_MUC) -> dict:
    """Law 9 verdict for a proposed verification budget on one job.

    The budget buys the strongest class it can afford on this job; the check passes
    only if running that class drives the expected fraud profit below zero. A budget
    below class-A cost means the job runs unverified: the whole value is stealable.
    """
    affordable = [c for c in ORDER
                  if price_verification(job_value_muc, c) <= verification_budget_muc]
    if not affordable:
        return {"law9_pass": False, "reason": "budget below class-A cost: unverified job",
                "max_profitable_fraud_muc": job_value_muc,
                "verification_budget_muc": verification_budget_muc}
    bought = affordable[-1]
    max_profit = max(expected_fraud_profit_muc(job_value_muc, bought, bond_cap_muc), 0)
    return {
        "law9_pass": max_profit == 0,
        "bought_class": bought,
        "max_profitable_fraud_muc": max_profit,
        "verification_budget_muc": verification_budget_muc,
        "margin_muc": verification_budget_muc
                      - price_verification(job_value_muc, bought),
        "reason": f"class {bought} drives expected fraud profit to {max_profit} µ¢"
                  if max_profit == 0 else
                  f"class {bought} leaves {max_profit} µ¢ expected fraud profit (Law 9)",
    }


def sample_for_reexecution(n_claims: int, seed: int, k: int | None = None) -> list[int]:
    """Deterministic sample of claim indices to re-execute (class C, mulberry32 —
    the anti-herd PRNG of Law 14; k defaults to ~10% with a floor of 1)."""
    from .antiherd import mulberry32
    if n_claims <= 0:
        return []
    k = k if k is not None else max(1, n_claims // 10)
    k = min(k, n_claims)
    rng = mulberry32(seed)
    idx = list(range(n_claims))
    for i in range(k):  # partial Fisher–Yates, deterministic
        j = i + next(rng) % (n_claims - i)
        idx[i], idx[j] = idx[j], idx[i]
    return sorted(idx[:k])
