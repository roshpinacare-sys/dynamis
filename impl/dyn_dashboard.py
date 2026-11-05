#!/usr/bin/env python3
"""dyn.dashboard.v1 — the honest-budget emission dashboard (gate 2.2, executable).

Gate 2.2's acceptance: *"dashboard shows emitted == revenue-verified"*. This module
computes that dashboard from a real market stream (the same JSONL the metrics read)
and renders it as a static page with the gaps unhidden:

  - **The Law-19 invariant, at µ¢ resolution** — emitted DYN must equal
    `(payout + fee) × 400` summed over settled jobs, refunds emit exactly zero.
    The dashboard recomputes both sides from the stream and **refuses to render
    a passing dashboard if the invariant breaks** — fail-closed, no cosmetic
    override (docs/02: the dashboard exists from Phase 1, gaps unhidden).
  - **Target vs measured** — the page carries the canonical rate next to the
    measured rate, and every divergence is a visible red line, not a footnote.
  - **Static and self-contained** — the HTML is stdlib-generated, inline CSS,
    no external resources (the same rules the site checker enforces).

Gate 2.2's world half (the ≥ 14 consecutive days) is calendar time; this module
is the measured artifact each day appends to.

  python3 dyn_market.py run --days 14 --out market.jsonl
  python3 dyn_dashboard.py from-stream market.jsonl --out site/dashboard.html

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_metrics import load_stream  # noqa: E402
from dynamis_core.canonical import object_hash  # noqa: E402
from dynamis_core.emission import DYN_MU_PER_USDS_MUC  # noqa: E402

DASHBOARD = "dyn.dashboard.v1"


class DashboardError(Exception):
    pass


def compute(stream_rows: list[dict]) -> dict:
    """The Law-19 numbers from settle/refund rows alone. Divisors guarded."""
    settles = [r for r in stream_rows if r.get("event") == "settle"]
    refunds = [r for r in stream_rows if r.get("event") == "refund"]
    opens = [r for r in stream_rows if r.get("event") == "open"]

    settled_muc = sum(r.get("payout_muc", 0) + r.get("fee_muc", 0) for r in settles)
    emitted_mu = sum(r.get("emitted_dyn_mu", 0) for r in settles)
    expected_mu = settled_muc * DYN_MU_PER_USDS_MUC
    refund_emits = [r for r in refunds if r.get("emitted_dyn_mu", 0) != 0]

    checks = {
        "emitted_eq_revenue": emitted_mu == expected_mu,
        "refund_emits_nothing": not refund_emits,
        "no_settlement_without_work": len(settles) <= len(opens),
    }
    m = {
        "dashboard": DASHBOARD, "rate": DYN_MU_PER_USDS_MUC,
        "jobs_opened": len(opens), "jobs_settled": len(settles),
        "jobs_refunded": len(refunds),
        "settled_revenue_muc": settled_muc, "emitted_dyn_mu": emitted_mu,
        "expected_dyn_mu": expected_mu, "checks": checks,
        "ok": all(checks.values()),
    }
    if not m["ok"]:
        raise DashboardError(
            "Law-19 invariant broken — refusing to render a passing dashboard: "
            + json.dumps({k: v for k, v in m.items() if k in
                          ("settled_revenue_muc", "emitted_dyn_mu",
                           "expected_dyn_mu", "checks")}))
    m["digest"] = object_hash({k: v for k, v in m.items() if k != "digest"})[:32]
    return m


def render(m: dict) -> str:
    """Honest-budget HTML: measured numbers, canonical rate beside them, gaps unhidden."""
    def n(x: int) -> str:
        return f"{x:,}"

    ok = m["ok"]
    badge = "#1d8f74" if ok else "#b3261e"
    rows = "".join(
        f"<tr><td>{label}</td><td class='num'>{value}</td></tr>"
        for label, value in (
            ("Jobs opened (work demanded by real budgets)", n(m["jobs_opened"])),
            ("Jobs settled (revenue-verified)", n(m["jobs_settled"])),
            ("Jobs refunded (escrow returned, nothing minted)", n(m["jobs_refunded"])),
            ("Settled revenue (payout + fee, µ¢)", n(m["settled_revenue_muc"])),
            ("Expected emission at the canonical rate (µDYN)", n(m["expected_dyn_mu"])),
            ("Measured emission (µDYN)", n(m["emitted_dyn_mu"])),
            ("Canonical rate (µDYN per µ¢)", n(m["rate"])),
        ))
    checks = "".join(
        f"<li class='{'pass' if v else 'fail'}'>{k}: {'measured OK' if v else 'BROKEN'}</li>"
        for k, v in m["checks"].items())
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DYNAMIS — emission dashboard</title>
<style>
body{{font:16px/1.6 system-ui,Georgia,serif;margin:0;background:#0b0f12;color:#e8e6e1}}
main{{max-width:860px;margin:0 auto;padding:48px 24px}}
h1{{font-size:1.7rem;margin:0 0 4px}} .sub{{color:#9aa3a9;margin-bottom:28px}}
.badge{{display:inline-block;padding:6px 14px;border-radius:999px;color:#fff;
background:{badge};font-weight:600;font-size:.9rem}}
table{{width:100%;border-collapse:collapse;margin:28px 0}}
td{{padding:10px 8px;border-bottom:1px solid #1f262b}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
ul{{list-style:none;padding:0}} li{{padding:8px 0;border-bottom:1px solid #1f262b}}
li.pass::before{{content:"✓ ";color:#3ecfb2}} li.fail::before{{content:"✗ ";color:#ff7b72}}
.foot{{color:#9aa3a9;font-size:.85rem;margin-top:32px}}
</style></head><body><main>
<h1>DYNAMIS — the emission dashboard</h1>
<div class="sub">Law 19, computed from a real market stream. Gaps are shown, not hidden.</div>
<span class="badge">{'INVARIANT HOLDS' if ok else 'INVARIANT BROKEN'}</span>
<table>{rows}</table>
<h2>Checks, as measured</h2>
<ul>{checks}</ul>
<p class="foot">dyn.dashboard.v1 · digest {escape(m.get('digest', ''))} ·
recomputed from the stream, not remembered · the world half of gate 2.2 is
14 consecutive days of this page staying true.</p>
</main></body></html>"""


def from_stream(path: str | Path, out: str | Path) -> dict:
    rows, _summary = load_stream(path)
    m = compute(rows)
    Path(out).write_text(render(m), encoding="utf-8")
    return m


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.dashboard.v1 — gate 2.2 executable")
    ap.add_argument("cmd", choices=["from-stream"])
    ap.add_argument("stream")
    ap.add_argument("--out", default="dashboard.html")
    ns = ap.parse_args(argv)
    if ns.cmd == "from-stream":
        m = from_stream(ns.stream, ns.out)
        print(f"dashboard written to {ns.out}: invariant {'holds' if m['ok'] else 'BROKEN'}, "
              f"emitted {m['emitted_dyn_mu']:,} µDYN on {m['settled_revenue_muc']:,} µ¢ "
              f"verified revenue (digest {m['digest']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
