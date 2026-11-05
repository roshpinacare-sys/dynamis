#!/usr/bin/env python3
"""dyn.metrics.v1 — validation metrics, computed from the market stream.

docs/13 §4 promises the validation table; Law 4 (measured, or it did not
happen) demands the numbers be *computed*, not asserted. This module reads a
dyn.market.v1 JSONL stream and returns the six metrics that say whether the
economy has demand — plus the stream-level forms of the Law-19 checks:

  jobs_per_day          entities actually have work (open rows / day)
  time_to_first_claim   agents are watching (open day → first work day, mean)
  pass_rate_by_class    the ladder prices verification honestly (settled/opened
                        per verification class, joined open → final outcome)
  failures_caught       refunds ÷ (settled + refunded) — attempts that failed
                        were caught *before* any payment
  payout_velocity       settled jobs per day — the economy pays, not just settles
  dyn_per_settled_usds  Law-19 coupling in flow: emitted DYN ÷ settled USDS
                        (payout + fee — the whole escrow that moved)

The stream is the source of truth: same seed, same stream, same numbers.

  python3 dyn_metrics.py market.jsonl
  python3 dyn_market.py run --days 14 --out market.jsonl && python3 dyn_metrics.py market.jsonl

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

METRICS = "dyn.metrics.v1"


def load_stream(path: str | Path) -> tuple[list[dict], dict | None]:
    """Parse a market JSONL file into (event rows, summary row or None)."""
    rows: list[dict] = []
    summary: dict | None = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "summary" in obj and "event" not in obj:
                summary = obj["summary"]
            else:
                rows.append(obj)
    return rows, summary


def compute_metrics(rows: list[dict], *, days: int | None = None) -> dict:
    """The validation table, computed from event rows alone.

    `days` overrides the span (defaults to the highest day seen, min 1).
    Every divisor is guarded: an empty or one-sided stream yields zeros,
    never a crash and never a NaN.
    """
    days = max(days or (max((r["day"] for r in rows), default=0) or 1), 1)

    opens = [r for r in rows if r["event"] == "open"]
    works = [r for r in rows if r["event"] == "work"]
    settles = [r for r in rows if r["event"] == "settle"]
    refunds = [r for r in rows if r["event"] == "refund"]

    # jobs per day — entities actually have work
    jobs_per_day = len(opens) / days

    # time to first claim — open day → first work day for that job
    open_day = {r["job"]: r["day"] for r in opens}
    claimed: dict[str, int] = {}
    for r in works:
        if r["job"] not in claimed and r["job"] in open_day:
            claimed[r["job"]] = r["day"]
    ttfc = [claimed[j] - open_day[j] for j in open_day if j in claimed]
    time_to_first_claim = (sum(ttfc) / len(ttfc)) if ttfc else 0.0

    # pass rate by class — join open → final outcome (settle wins over refund)
    cls_of = {r["job"]: r.get("cls") for r in opens}
    outcome: dict[str, str] = {}
    for r in rows:
        if r["event"] == "settle":
            outcome[r["job"]] = "settled"
        elif r["event"] == "refund":
            outcome.setdefault(r["job"], "refunded")
    by_cls: dict[str, dict] = {}
    for job, cls in sorted(cls_of.items(), key=lambda kv: str(kv[1])):
        bucket = by_cls.setdefault(str(cls), {"opened": 0, "settled": 0})
        bucket["opened"] += 1
        if outcome.get(job) == "settled":
            bucket["settled"] += 1
    for b in by_cls.values():
        b["pass_rate"] = round(b["settled"] / b["opened"], 4) if b["opened"] else 0.0

    # failures caught before payment
    attempts = len(settles) + len(refunds)
    failures_caught = round(len(refunds) / attempts, 4) if attempts else 0.0

    # payout velocity — settles per day, and mean payout per settled job
    payout_velocity = len(settles) / days
    payouts = [r.get("payout_usds", 0) for r in settles]
    mean_payout_usds = (sum(payouts) / len(payouts)) if payouts else 0.0

    # Law-19 coupling in flow
    emitted_mu = sum(r.get("emitted_dyn_mu", 0) for r in settles)
    settled_usds = sum(r.get("payout_usds", 0) + r.get("fee_usds", 0) for r in settles)
    dyn_per_settled_usds = round(emitted_mu / 1_000_000 / settled_usds, 4) if settled_usds else 0.0

    # stream-level forms of the laws (checkable from the stream alone)
    laws = {
        "no_payout_without_emission": all(r.get("emitted_dyn_mu", 0) > 0 for r in settles),
        "refund_emits_nothing": all(r.get("emitted_dyn_mu", 0) == 0 for r in refunds),
        "no_settle_without_work": _no_settle_without_work(rows),
    }
    return {
        "metrics": METRICS,
        "days": days,
        "jobs_opened": len(opens),
        "jobs_per_day": round(jobs_per_day, 4),
        "time_to_first_claim_days": round(time_to_first_claim, 4),
        "pass_rate_by_class": by_cls,
        "failures_caught": failures_caught,
        "payout_velocity_per_day": round(payout_velocity, 4),
        "mean_payout_usds": round(mean_payout_usds, 2),
        "emitted_dyn": emitted_mu / 1_000_000,
        "settled_usds": settled_usds,
        "dyn_per_settled_usds": dyn_per_settled_usds,
        "laws": laws,
    }


def _no_settle_without_work(rows: list[dict]) -> bool:
    worked: set[str] = set()
    for r in rows:
        if r["event"] == "work":
            worked.add(r["job"])
        elif r["event"] == "settle" and r["job"] not in worked:
            return False
    return True


def report(m: dict) -> str:
    lines = [
        f"{METRICS} — {m['jobs_opened']} jobs over {m['days']} days",
        f"  jobs/day            {m['jobs_per_day']}",
        f"  time-to-first-claim {m['time_to_first_claim_days']} d",
        "  pass rate by class  " + ", ".join(
            f"{cls}: {b['settled']}/{b['opened']} ({b['pass_rate']:.0%})"
            for cls, b in m["pass_rate_by_class"].items()) or "  (no classes)",
        f"  failures caught     {m['failures_caught']:.1%}",
        f"  payout velocity     {m['payout_velocity_per_day']}/day "
        f"(mean payout {m['mean_payout_usds']} USDS)",
        f"  emission coupling   {m['emitted_dyn']:,.0f} DYN / {m['settled_usds']:,.0f} USDS "
        f"= {m['dyn_per_settled_usds']} DYN per settled USDS",
        "  laws: " + ", ".join(f"{k}={v}" for k, v in m["laws"].items()),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dyn_metrics", description="DYNAMIS validation metrics (dyn.metrics.v1)")
    ap.add_argument("stream", help="market JSONL stream (from dyn_market run --out)")
    a = ap.parse_args(argv)
    rows, summary = load_stream(a.stream)
    days = summary["days"] if summary else None
    m = compute_metrics(rows, days=days)
    print(report(m))
    if summary:
        agree = all(summary["laws"].values()) and all(m["laws"].values())
        print(f"  stream summary agrees with computed laws: {agree}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
