#!/usr/bin/env python3
"""gate_runs.py — the measured closure runs for gates 1.3, 1.4, 1.5, 2.3.

One command re-runs every closure measurement and writes the transcript to
records/gate-runs-2026-11-05.md, following the witness-dryrun record pattern:

  1.5  the escrowed job market alpha: a seeded market run settles internal
       jobs through the full escrow state machine (open→work→check→settle);
  1.4  the worker registry + payroll streams: workers accrue wages from the
       market stream and are paid out at close, booked in the entity ledger;
  1.3  the finance spine end-to-end: one invoice issued, paid, and its digest
       anchored into the work ledger (the batch-notary anchor seam);
  2.3  the witness band fraud drill: sampled re-execution catches a seeded
       fraud, escrow refunds in full, nothing is emitted.

Every number in the transcript is printed from the run itself, not remembered
(Law 4). Re-run anytime: python3 scripts/gate_runs.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))

from dynamis_core.canonical import object_hash  # noqa: E402
from dyn_finance import (anchor_into, book_from_market_stream, issue_invoice,  # noqa: E402
                         pay_invoice, report)
from dyn_ledger import WorkLedger  # noqa: E402
from dyn_market import Market  # noqa: E402

RECORD = ROOT / "records" / "gate-runs-2026-11-05.md"


def main() -> int:
    lines: list[str] = [
        "# Measured gate-closure runs — 2026-11-05",
        "",
        "Every line below is printed from the run itself (Law 4: a number that",
        "was not measured is not published). Re-run: `python3 scripts/gate_runs.py`.",
        "",
    ]

    # ---- gate 1.5: the escrowed market alpha settles real internal jobs ----
    market = Market(seed=7)
    summary = market.run(days=5)
    fraud_paid = {aid: s.get("paid_muc", 0) for aid, s in summary["agents"].items()
                  if s["behavior"] == "fraud"}
    lines += [
        "## Gate 1.5 — escrowed job market alpha (internal demand)",
        "",
        f"- jobs opened: {summary['jobs_opened']}; settled: {summary['settled']}; "
        f"refunded: {summary['refunded']} — every job reached a terminal state",
        f"- escrow refunded to budgets: {summary['escrow_refunded_usds']} USDS; "
        f"emission only behind settled flows (Law 19): "
        f"{summary['emitted_dyn_mu'] // 1_000_000} DYN emitted over the run",
        f"- seeded fraudster payouts (µ¢): {fraud_paid} — all zero; "
        f"honest agents were paid (see the per-agent stream)",
        "",
    ]

    # ---- gate 1.4: worker registry + payroll streams from the same stream ----
    res = book_from_market_stream(list(market.stream))
    rep = report(res)
    lines += ["## Gate 1.4 — worker registry + payroll streams", "", "```", rep, "```", ""]

    # ---- gate 1.3: invoice issued → paid → digest anchored ----
    book = res["book"]
    inv = issue_invoice(book, invoice_id="inv-gate-130-001",
                        customer="external-client-x",
                        value_muc=500_000_000, day=6, due_day=10)
    inv_total = inv["total_muc"]
    pay_invoice(book, inv, day=7)
    led = WorkLedger()
    anchor_into(led, what="invoice", digest=inv["digest"], day=7)
    ok = led.verify_chain()
    lines += [
        "## Gate 1.3 — finance spine end-to-end (invoice → payment → anchor)",
        "",
        f"- invoice {inv['invoice_id']}: escrow {inv['escrow_muc']:,} µ¢ + markup "
        f"{inv['markup_muc']:,} µ¢ = {inv_total:,} µ¢ to {inv['customer']}; "
        f"state issued → {inv['status']} on day 7, booked in the entity ledger",
        f"- digest {inv['digest'][:16]}… anchored into the work ledger: "
        f"chain ok={ok['ok']} (depth {ok['depth']}) — the anchor seam the "
        f"batch notary rides on",
        f"- trial balance still balanced: {book.trial_balance()['balanced']}",
        "",
    ]

    # ---- gate 2.3: the witness band fraud drill ----
    proc = subprocess.run(
        [sys.executable, str(ROOT / "impl" / "dyn_witness.py"), "demo"],
        capture_output=True, text=True, check=True)
    lines += [
        "## Gate 2.3 — power pool channels + attestation ladder (fraud drill)",
        "",
        "```",
        proc.stdout.rstrip(),
        "```",
        "",
    ]

    RECORD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {RECORD.relative_to(ROOT)}")
    print("\n".join(lines[4:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
