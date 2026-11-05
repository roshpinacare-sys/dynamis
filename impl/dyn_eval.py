#!/usr/bin/env python3
"""dyn.eval.v1 — the evaluation market (gate 3.2, executable).

Self-reported evaluation is worthless (docs/06: it is vote-buying wearing a
suit). Verification is a paid, bond-scored job instead (Laws 8, 13):

  - **Evaluator registry** — an evaluator joins with a bond in µ¢. No bond,
    no seat; the bond is the skin in the game.
  - **Questions with withheld ground truth** — a question opens with its verdict
    sealed; evaluators submit verdict + confidence (bps); on close the outcome
    is revealed and scoring runs through `dynamis_core.brier` (integer math).
  - **Correct verdicts earn the fee** (3% of bond); **wrong ones burn bond**
    proportional to how confidently wrong they were (brier × K, capped).
  - **The calibration report is published whatever it shows** — the
    no-embarrassment clause is honored in code: the report includes the worst
    bucket by mean Brier score and the market ECE. Gaps are shown, not hidden.

Gate 3.2 acceptance: the calibration report is generated from scored verdicts
and *published* (written to `specs/acceptance/` by the evidence run).

  python3 dyn_eval.py demo     # a scored market with the report printed

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.brier import (brier_score, calibration_bucket,  # noqa: E402
                                eval_payout, expected_calibration_error)
from dynamis_core.canonical import object_hash  # noqa: E402

EVAL = "dyn.eval.v1"
GENESIS = "0" * 64
MIN_BOND_MUC = 500_000_000          # $500 minimum bond for a seat


class EvalError(Exception):
    pass


class EvalMarket:
    """One question, bond-scored evaluators, published calibration."""

    def __init__(self, question_id: str, *, ground_truth: str, day: int) -> None:
        if ground_truth not in ("pass", "fail"):
            raise EvalError("ground truth must be pass|fail")
        self.question_id = question_id
        self._truth = ground_truth            # withheld until close()
        self.day = day
        self.evaluators: dict[str, int] = {}  # agent_id -> bond_muc
        self.verdicts: list[dict] = []
        self.closed = False
        self.rows: list[dict] = []

    def register(self, agent_id: str, bond_muc: int) -> dict:
        if self.closed:
            raise EvalError("market closed")
        if bond_muc < MIN_BOND_MUC:
            raise EvalError(f"bond below seat minimum: {bond_muc} µ¢ < {MIN_BOND_MUC} µ¢")
        self.evaluators[agent_id] = bond_muc
        return {"agent": agent_id, "bond_muc": bond_muc}

    def submit(self, agent_id: str, verdict: str, confidence_bps: int) -> dict:
        if self.closed:
            raise EvalError("market closed")
        if agent_id not in self.evaluators:
            raise EvalError(f"{agent_id} has no seat (no bond, no verdict)")
        if verdict not in ("pass", "fail"):
            raise EvalError("verdict must be pass|fail")
        if not isinstance(confidence_bps, int) or not 0 <= confidence_bps <= 10000:
            raise EvalError("confidence_bps must be an integer in [0, 10000]")
        if any(v["agent"] == agent_id for v in self.verdicts):
            raise EvalError(f"{agent_id} already submitted — one verdict per seat")
        row = {"agent": agent_id, "verdict": verdict, "confidence_bps": confidence_bps}
        row["digest"] = object_hash(row)[:16]
        self.verdicts.append(row)
        return row

    def close(self) -> dict:
        """Reveal the outcome, score every seat, publish the calibration report."""
        if not self.verdicts:
            raise EvalError("no verdicts submitted — nothing to score")
        scored: list[dict] = []
        buckets: dict[str, list[int]] = {}
        for v in self.verdicts:
            score = brier_score(v["confidence_bps"], v["verdict"], self._truth)
            pay = eval_payout(self.evaluators[v["agent"]], score, self._truth, v["verdict"])
            scored.append({**v, "score_bps": score, **pay})
            b = calibration_bucket(v["confidence_bps"])
            buckets.setdefault(b, []).append(score)
        bucket_means = {b: (sum(s) // len(s), len(s)) for b, s in sorted(buckets.items())}
        ece = expected_calibration_error(bucket_means)
        worst = max(bucket_means.items(), key=lambda kv: kv[1][0])
        self.closed = True
        self.rows = scored
        report = {
            "market": EVAL, "question": self.question_id, "day": self.day,
            "truth": self._truth, "seats": len(self.evaluators),
            "ece_bps": ece,
            "worst_bucket": {"bucket": worst[0], "mean_score_bps": worst[1][0],
                             "count": worst[1][1]},
            "burned_muc": sum(r["burn_muc"] for r in scored),
            "fees_muc": sum(r["fee_muc"] for r in scored),
            "no_embarrassment_clause": "published as measured, gaps included",
        }
        report["digest"] = object_hash({k: v for k, v in report.items()
                                        if k != "digest"})[:32]
        self.report = report
        return {"scored": scored, "report": report}


def demo() -> str:
    """Three seats: one calibrated, one overconfident-wrong, one honest."""
    m = EvalMarket("q-001", ground_truth="pass", day=30)
    m.register("eval-calibrated", 2_000_000_000)
    m.register("eval-overconfident", 2_000_000_000)
    m.register("eval-honest", 1_000_000_000)
    m.submit("eval-calibrated", "pass", 8_000)
    m.submit("eval-overconfident", "fail", 9_600)
    m.submit("eval-honest", "pass", 6_500)
    out = m.close()
    rep = out["report"]
    return (f"seats: {rep['seats']}, truth: {rep['truth']}, ECE {rep['ece_bps']} bps, "
            f"worst bucket {rep['worst_bucket']['bucket']} "
            f"({rep['worst_bucket']['mean_score_bps']} bps mean), "
            f"burned {rep['burned_muc']} µ¢, fees {rep['fees_muc']} µ¢\n"
            f"report digest {rep['digest']} — published with gaps included")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.eval.v1 — gate 3.2 executable")
    ap.add_argument("cmd", choices=["demo"])
    ns = ap.parse_args(argv)
    if ns.cmd == "demo":
        print(demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
