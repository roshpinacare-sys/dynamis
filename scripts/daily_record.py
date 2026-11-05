#!/usr/bin/env python3
"""daily_record.py — one dated, measured record per day (the calendar halves of the gates).

Gate 1.1 wants "≥ 99% uptime measured over 7 consecutive days"; gate 2.2 wants
"the dashboard true over ≥ 14 consecutive days". Calendar windows cannot be
faked or back-filled — they can only be *kept*. This script keeps them: each
day it runs the real loops (market simulation with a fixed seed, the Law-19
dashboard recomputation, the six metrics, the heartbeat) and writes a dated
record under `records/<date>/`:

    records/2026-11-06/dashboard.html   the honest dashboard as of that day
    records/2026-11-06/metrics.txt      the six numbers, as measured
    records/2026-11-06/summary.json     hash-stamped facts, gaps unhidden

A missing day is a visible hole in the record — which is exactly the point.
The `daily-proof` workflow runs this at 00:05 UTC and commits the record, so
the 14-day window accrues in-repo, in public.

  python3 scripts/daily_record.py --date 2026-11-06 --out records

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))
sys.path.insert(0, str(ROOT / "scripts"))

from dyn_dashboard import compute as law19  # noqa: E402
from dyn_dashboard import render  # noqa: E402
from dyn_metrics import compute_metrics, load_stream, report  # noqa: E402
from heartbeat import beat  # noqa: E402

RECORD = "dyn.daily-record.v1"
DEFAULT_SEED = 20261106               # fixed seed: day-over-day numbers comparable
SIM_DAYS = 14


def build_record(date: str, *, out_dir: Path, seed: int = DEFAULT_SEED,
                 sim_days: int = SIM_DAYS) -> dict:
    day_dir = out_dir / date
    day_dir.mkdir(parents=True, exist_ok=True)

    hb = beat()
    with tempfile.TemporaryDirectory() as td:
        stream = Path(td) / "market.jsonl"
        subprocess.run(
            [sys.executable, str(ROOT / "impl" / "dyn_market.py"), "run",
             "--days", str(sim_days), "--seed", str(seed), "--out", str(stream)],
            check=True, capture_output=True)
        rows, summary = load_stream(stream)
        metrics = compute_metrics(rows)
        law = law19(rows)                    # raises if the invariant breaks

    (day_dir / "dashboard.html").write_text(render(law), encoding="utf-8")
    (day_dir / "metrics.txt").write_text(report(metrics) + "\n", encoding="utf-8")

    rec = {
        "record": RECORD, "date": date, "seed": seed, "sim_days": sim_days,
        "heartbeat_ok": hb["ok"],
        "jobs_opened": metrics["jobs_opened"], "jobs_settled": law["jobs_settled"],
        "jobs_refunded": law["jobs_refunded"],
        "settled_revenue_muc": law["settled_revenue_muc"],
        "emitted_dyn_mu": law["emitted_dyn_mu"],
        "law19_ok": law["ok"],
        "market_emitted_dyn_mu": (summary or {}).get("emitted_dyn_mu", 0),
        "market_laws": (summary or {}).get("laws", {}),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    from dynamis_core.canonical import object_hash
    rec["record_digest"] = object_hash(
        {k: v for k, v in rec.items() if k != "record_digest"})[:32]
    (day_dir / "summary.json").write_text(
        json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the daily measured record")
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=str(ROOT / "records"))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ns = ap.parse_args(argv)
    rec = build_record(ns.date, out_dir=Path(ns.out), seed=ns.seed)
    print(json.dumps(rec))
    return 0 if rec["law19_ok"] and rec["heartbeat_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
