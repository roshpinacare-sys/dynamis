"""Evaluator scoring — Brier + bond math (docs/03 §6).

Evaluation is a paid, bond-scored job. Evaluators report a verdict with confidence
(bps); the Brier score against the observed outcome drives bond burn and fee payout.
Calibration is published (Gate 3.2) — the no-embarrassment clause means gaps are shown,
not hidden (Law 8).
"""
from __future__ import annotations

from .canonical import bps_of

BURN_K_BPS = 4000  # bond burn = bond × brier × K (K=0.4); capped at the bond itself
FEE_ON_CORRECT_BPS = 300  # eval fee: 3% of the bond on a correct verdict


def brier_score(confidence_bps: int, verdict: str, observed: str) -> int:
    """Multiplied Brier in bps: 0 = perfect, 10000 = perfectly wrong.

    p = confidence if verdict == 'pass' else 1 - confidence;
    outcome = 1 if observed == 'pass' else 0.
    score_bps = ((p - outcome)^2) × 10000, integer math throughout.
    """
    if verdict not in ("pass", "fail") or observed not in ("pass", "fail"):
        raise ValueError("verdict/observed must be pass|fail")
    if not 0 <= confidence_bps <= 10000:
        raise ValueError("confidence_bps out of range")
    p = confidence_bps if verdict == "pass" else 10000 - confidence_bps
    outcome = 10000 if observed == "pass" else 0
    return (p - outcome) ** 2 // 10000


def bond_burn(bond_muc: int, score_bps: int) -> int:
    """µ¢ burned from the evaluator bond for one verdict: bond × K × brier,
    K = BURN_K_BPS/10000, capped at the bond itself."""
    if score_bps < 0 or score_bps > 10000:
        raise ValueError("score_bps out of range")
    inner = BURN_K_BPS * score_bps // 10000          # K applied to the score
    return min(bps_of(bond_muc, inner), bond_muc)


def eval_payout(bond_muc: int, score_bps: int, observed: str, verdict: str) -> dict:
    """Fee or burn for one evaluation. Correct verdicts earn the fee; wrong ones burn
    bond proportional to how confidently wrong they were."""
    correct = (verdict == observed)
    if correct:
        return {"fee_muc": bps_of(bond_muc, FEE_ON_CORRECT_BPS), "burn_muc": 0}
    return {"fee_muc": 0, "burn_muc": bond_burn(bond_muc, score_bps)}


def calibration_bucket(confidence_bps: int) -> str:
    """Ten confidence buckets for the published calibration report (Gate 3.2)."""
    if not 0 <= confidence_bps <= 10000:
        raise ValueError("confidence_bps out of range")
    lo = confidence_bps // 1000 * 10
    return f"{lo:02d}-{lo + 10:02d}"


def expected_calibration_error(buckets: dict[str, tuple[int, int]]) -> int:
    """ECE in bps from {bucket: (mean_score_bps, count)}; integer weighted mean."""
    total = sum(c for _, c in buckets.values())
    if total == 0:
        raise ValueError("no evaluations to calibrate")
    acc = 0
    for mean_score, count in buckets.values():
        acc += mean_score * count
    return acc // total
