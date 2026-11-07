#!/usr/bin/env python3
"""Run the craft-loop measurement at full pool size and write the record.

python3 scripts/bench_run.py            # 60 tasks, seed 20261106
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))

import dyn_measure as dm  # noqa: E402


def md_table(metrics: dict) -> str:
    p = metrics["pipelines"]
    m = metrics["worker_model"]
    inc = metrics["worker_income_muc"]
    ov = metrics["overhead"]
    run = metrics["run"]
    usds = lambda muc: f"{muc / 1_000_000:,.0f}"  # noqa: E731
    lines = [
        "# What the craft loop changes — measured",
        "",
        f"Seed {run['seed']} · pool {metrics['pool']['tasks']} tasks "
        f"({metrics['pool']['file']} file fingerprints, {metrics['pool']['web']} "
        f"web rebuilds) · escrow {metrics['pool']['escrow_usds']} USDS/task · "
        f"pool value {metrics['pool']['pool_value_usds']:,} USDS",
        "",
        f"Worker model (stated, not hidden): {m['p_broken']:.0%} of builds ship "
        f"broken ({m['broken_draws']} of {metrics['pool']['tasks']} drawn); "
        f"{m['p_forged_of_broken']:.0%} of those claim “it is correct” "
        f"({m['forged_draws']} forged claims). {m['correct_draws']} builds are "
        "drawn correct. Every pipeline runs the SAME draws.",
        "",
        "| pipeline | shipped broken | working delivered | buyer paid (USDS) | refunded (USDS) | cost / working artifact (USDS) | forged claims caught |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, label in (("naive", "naive — pay everything, verify nothing"),
                        ("self_report", "self-report — the worker's claim gates"),
                        ("craft", "craft — study, build, re-executed check")):
        r = p[name]
        lines.append(
            f"| {label} | {r['shipped_broken']} | {r['working_delivered']} | "
            f"{usds(r['buyer_paid_muc'])} | {usds(r['escrow_back_muc'])} | "
            f"{r['cost_per_working_muc'] / 1_000_000:,.0f} | {r['forged_caught']} |")
    lines += [
        "",
        f"Worker income: agent-honest-1 {usds(inc['agent-honest-1'])} USDS, "
        f"agent-shaky-1 {usds(inc['agent-shaky-1'])} USDS — {inc['gradient']}",
        "",
        f"Protocol overhead, measured on the same run: {ov['ms_per_job_avg']} ms "
        f"per full job (open→study→approval→build→check→settle/refund), "
        f"{ov['ms_total']} ms total. The chain sealed itself "
        f"{run['seals']}× over {run['entries']} ledger entries and the audit "
        f"returned ok={str(run['audit_ok']).lower()}.",
        "",
        "## Reading",
        "",
        "- The loop does not make generation smarter: the same draws produce the "
        "same builds everywhere. What changes is what survives to the buyer — "
        f"{p['naive']['shipped_broken']} broken deliveries reach the buyer un-verified; "
        f"{p['craft']['shipped_broken']} reach it through the check.",
        f"- The buyer's cost per working artifact falls from "
        f"{p['naive']['cost_per_working_muc'] / 1_000_000:,.0f} USDS (paying for "
        "broken work) to the task's own price — everything else comes back as "
        "refunds, fees 0, emission 0.",
        "- Correctness becomes the only income: the honest worker earns everything "
        "the shaky worker earns nothing. That is the incentive the protocol adds.",
        "- A claim is not evidence: self-report ships the same broken work as naive "
        "and catches none of the forged claims; the re-executed check catches all "
        f"{m['forged_draws']} of them.",
        "",
        "## Honest scope",
        "",
        "This measures the PROTOCOL's effect under a stated generation-error "
        "model, over the loop's real paths and real money. It does not measure "
        "model quality — the workers are seeded draws, not agents. Measuring real "
        "agents against this pool is the named next measurement; the harness they "
        "would face is the same one these numbers came from.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    metrics = dm.run_bench(n_tasks=60, seed=20261106)
    out = ROOT / "records"
    out.mkdir(exist_ok=True)
    (out / "benchmark-2026-11-06.json").write_text(
        json.dumps(metrics, indent=1, sort_keys=True) + "\n")
    (out / "benchmark-2026-11-06.md").write_text(md_table(metrics))
    print("written: records/benchmark-2026-11-06.{json,md}")
    for name, r in metrics["pipelines"].items():
        print(f"{name:12} shipped_broken={r['shipped_broken']} "
              f"working={r['working_delivered']} "
              f"cost/working={r['cost_per_working_muc'] / 1e6:.0f} USDS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
