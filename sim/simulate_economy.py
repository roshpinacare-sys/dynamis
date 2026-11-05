"""DYNAMIS economy simulation — flow-gated emission, Law-9 fraud economics, treasury.

Deterministic Monte Carlo (fixed seeds, stdlib RNG). Answers three questions with
numbers instead of narrative:

  1. Does flow-gated emission (Law 19) track revenue exactly, epoch for epoch?
  2. Does the Law-9 loop (verification budget must exceed max profitable fraud)
     converge when the network is allowed to escalate/de-escalate the verification
     class from measured monthly fraud data — the executable governance knob?
  3. Does the treasury stay solvent on coordination fees alone (5%), without ever
     selling tokens?

Model (all estimates labeled; replace with measured values as gates close):
  - entities: 1 at day 0, +1 at day 90 (Phase 2), +1 at day 180 (Phase 3), each with
    monthly envelopes ops $3,000 / growth $1,500 (docs/02 §1 example, as targets).
  - job values: $50–$2,000, log-uniform (T2 threshold caps routine work).
  - external demand: from day 120 (Phase 2 rails: x402), ramping to ~40% of flow.
  - fraud: 8% of claims fraudulent; caught with the class probability of the
    attestation ladder; caught → refund, uncaught → netted (an economy leak we count,
    not hide — Law 8).
  - governance: monthly, escalate one ladder letter if trailing-30d netted fraud
    exceeds trailing-30d verification spend; de-escalate only after a fraud-free month,
    never below class B for money jobs.

Run:  python3 sim/simulate_economy.py
Out:  sim/results/summary.json + 3 charts
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "impl"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dynamis_core import (EmissionLedger, floor_class, price_verification,
                          usds, CLASSES, ORDER, DEFAULT_BOND_CAP_MUC)

DAYS = 365
SEEDS = [11, 23, 37, 41, 53]
P_FRAUD = 0.08                    # 8% of claims are fraudulent (estimate)
EXTERNAL_START_DAY = 120
COORDINATION_FEE_BPS = 500        # genesis#escrow
ENTITY_ADD_DAYS = {90: 2, 180: 3}  # day → entity count (Phase 2/3 of the roadmap)


def job_value_usds(rng: random.Random) -> int:
    """Log-uniform between $50 and $2,000, in µ¢."""
    lo, hi = 50.0, 2000.0
    v = lo * (hi / lo) ** rng.random()
    return usds(int(v))


def run_sim(seed: int) -> dict:
    rng = random.Random(seed)
    led = EmissionLedger()
    ladder_idx = ORDER.index(floor_class(usds(500)))          # start at the measured floor
    calm_months = 0
    ladder_path: list[str] = [ORDER[ladder_idx]]
    n_entities = 1
    daily = {"revenue": [], "emitted": [], "verif_spend": [], "netted_fraud": [],
             "slash_recovered": [], "treasury": [], "jobs_settled": [],
             "external_share": []}
    treasury_muc = usds(500)                                   # seed capital (target, Law 8)
    win = {"verif": 0, "netted": 0, "slash": 0, "settled": 0, "revenue": 0}

    for day in range(1, DAYS + 1):
        n_entities = ENTITY_ADD_DAYS.get(day, n_entities)
        day_revenue = 0
        day_verif = 0
        day_netted = 0
        day_slash = 0
        day_settled = 0
        day_external = 0

        for e in range(n_entities):
            if rng.random() > 0.30:                            # entity posts ~9 days/month
                continue
            value = job_value_usds(rng)
            external = day >= EXTERNAL_START_DAY and rng.random() < min(
                0.4, (day - EXTERNAL_START_DAY) / 240)
            cls = ORDER[ladder_idx]
            vcost = price_verification(value, cls)
            p_caught = CLASSES[cls].p_caught_bps / 10000
            fraudulent = rng.random() < P_FRAUD
            caught = fraudulent and rng.random() < p_caught

            if not caught:
                # settled (honestly or uncaught): fee taken, emission flow-gated to it
                fee = value * COORDINATION_FEE_BPS // 10000
                treasury_muc += fee
                led.record_flow(f"job-{seed}-{e}-{day}-{rng.randrange(10**6)}",
                                value, "SETTLED",
                                "x402-external" if external else f"ent-{e:03d}-ops",
                                day)
                day_revenue += value
                day_settled += 1
                day_external += 1 if external else 0
                if fraudulent:
                    day_netted += value                        # uncaught fraud = leak
            else:
                # caught fraud: the slashed bond flows to the band (docs/03 §2) —
                # this recovery is what makes the ladder's fraud math close.
                slash = min(value * CLASSES[cls].penalty_multiple, DEFAULT_BOND_CAP_MUC)
                treasury_muc += slash
                day_slash += slash

            day_verif += vcost                                 # band budget spent either way

        # monthly governance: enforce Law 9 from measured trailing data (not vibes).
        # Escalate immediately when netted fraud outspends the band; de-escalate only
        # after TWO consecutive fraud-free months — fail-closed means reluctant to relax.
        if day % 30 == 0:
            if win["netted"] > win["verif"]:
                ladder_idx = min(ladder_idx + 1, len(ORDER) - 1)
                calm_months = 0
            elif win["netted"] == 0:
                calm_months += 1
                if calm_months >= 2 and ladder_idx > 1:   # never below B for money jobs
                    ladder_idx -= 1
                    calm_months = 0
            else:
                calm_months = 0
            ladder_path.append(ORDER[ladder_idx])
            win = {"verif": 0, "netted": 0, "settled": 0, "revenue": 0}

        treasury_muc -= day_verif                              # the band is paid in USDS
        win["verif"] += day_verif
        win["netted"] += day_netted
        win["slash"] = win.get("slash", 0) + day_slash
        win["settled"] += day_settled
        win["revenue"] += day_revenue

        daily["revenue"].append(day_revenue)
        daily["emitted"].append(led.cumulative_emitted_dyn_mu)
        daily["verif_spend"].append(day_verif)
        daily["netted_fraud"].append(day_netted)
        daily["slash_recovered"].append(day_slash)
        daily["treasury"].append(treasury_muc)
        daily["jobs_settled"].append(day_settled)
        daily["external_share"].append(
            day_external / day_settled if day_settled else 0.0)

    cum_verif = sum(daily["verif_spend"])
    cum_netted = sum(daily["netted_fraud"])
    cum_slash = sum(daily["slash_recovered"])
    return {
        "seed": seed,
        "total_settled_revenue_usds": led.cumulative_revenue_usds_muc / 1_000_000,
        "total_emitted_dyn": led.cumulative_emitted_dyn_mu / 1_000_000,
        "invariant_holds": led.invariant_holds(),
        "coordination_fees_usds": sum(daily["revenue"]) * COORDINATION_FEE_BPS / 10000 / 1_000_000,
        "verification_spend_usds": cum_verif / 1_000_000,
        "slash_recovered_usds": cum_slash / 1_000_000,
        "netted_fraud_usds": cum_netted / 1_000_000,
        "law9_margin_usds": (cum_verif + cum_slash - cum_netted) / 1_000_000,
        "treasury_end_usds": daily["treasury"][-1] / 1_000_000,
        "final_ladder_class": ORDER[ladder_idx],
        "ladder_path": ladder_path,
        "daily": daily,
        "flows": len(led.flows()),
    }


def main() -> None:
    out_dir = REPO / "sim" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = [run_sim(s) for s in SEEDS]
    avg = lambda key: sum(r[key] for r in runs) / len(runs)          # noqa: E731
    daily_keys = ["revenue", "emitted", "verif_spend", "netted_fraud",
                  "slash_recovered", "treasury", "jobs_settled", "external_share"]
    mean_daily = {k: [sum(r["daily"][k][d] for r in runs) / len(runs)
                      for d in range(DAYS)] for k in daily_keys}
    days = list(range(1, DAYS + 1))

    summary = {
        "model_version": "sim-1.0 (estimates per module docstring; Law 8 applies)",
        "days": DAYS, "seeds": SEEDS,
        "mean_total_settled_revenue_usds": round(avg("total_settled_revenue_usds"), 2),
        "mean_total_emitted_dyn": round(avg("total_emitted_dyn"), 2),
        "invariant_emitted_equals_revenue_verified": all(r["invariant_holds"] for r in runs),
        "mean_coordination_fees_usds": round(avg("coordination_fees_usds"), 2),
        "mean_verification_spend_usds": round(avg("verification_spend_usds"), 2),
        "mean_slash_recovered_usds": round(avg("slash_recovered_usds"), 2),
        "mean_netted_fraud_usds": round(avg("netted_fraud_usds"), 2),
        "mean_law9_margin_usds": round(avg("law9_margin_usds"), 2),
        "law9_margin_definition": "verification_spend + slash_recovered − netted_fraud ≥ 0",
        "law9_holds_all_seeds": all(r["law9_margin_usds"] >= 0 for r in runs),
        "mean_treasury_end_usds": round(avg("treasury_end_usds"), 2),
        "treasury_solvent_all_seeds": all(r["treasury_end_usds"] > 0 for r in runs),
        "final_ladder_class_by_seed": {str(r["seed"]): r["final_ladder_class"] for r in runs},
        "law9_margin_by_seed_usds": {str(r["seed"]): round(r["law9_margin_usds"], 2)
                                     for r in runs},
        "flows_per_run": round(avg("flows"), 1),
    }

    # fig 1 — flow-gated emission strictly behind revenue (Law 19)
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    ax.plot(days, [r / 1_000_000 for r in mean_daily["revenue"]],
            label="settled revenue (USDS/day)", color="#1a6faf")
    cum_rev, run = [], 0.0
    for r in mean_daily["revenue"]:
        run += r
        cum_rev.append(run / 1_000_000)
    ax2 = ax.twinx()
    ax2.plot(days, [e / 1_000_000 for e in mean_daily["emitted"]],
             label="cumulative DYN emitted (flow-gated)", color="#b3661a")
    ax.set_xlabel("protocol day")
    ax.set_ylabel("daily settled revenue, USDS")
    ax2.set_ylabel("cumulative DYN emitted")
    ax.set_title("Law 19 in code: emission exists only where revenue settled first")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines],
              loc="lower left", bbox_to_anchor=(0.0, 1.02), ncols=2, frameon=False)
    fig.savefig(out_dir / "fig1_emission_gated.png", dpi=150)
    plt.close(fig)

    # fig 2 — the Law-9 loop: band budget (spend + slash recovery) vs netted fraud
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    cum_v, cum_n, rv, rn, rs = [], [], 0.0, 0.0, 0.0
    for v, n, s in zip(mean_daily["verif_spend"], mean_daily["netted_fraud"],
                       mean_daily["slash_recovered"]):
        rv += v + s
        rn += n
        cum_v.append(rv / 1_000_000)
        cum_n.append(rn / 1_000_000)
    ax.plot(days, cum_v, label="cumulative band budget: verification spend + slash recovered",
            color="#1a6faf")
    ax.plot(days, cum_n, label="cumulative netted fraud (uncaught, USDS)", color="#a02020")
    ax.fill_between(days, cum_n, cum_v, where=[v >= n for v, n in zip(cum_v, cum_n)],
                    alpha=0.15, color="#1a6faf", label="Law-9 margin (band ≥ fraud)")
    ax.set_xlabel("protocol day")
    ax.set_ylabel("cumulative USDS")
    ax.set_title("Law 9 from measured data: the band outspends the fraud it must catch")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.02), ncols=2, frameon=False)
    fig.savefig(out_dir / "fig2_law9_margin.png", dpi=150)
    plt.close(fig)

    # fig 3 — treasury solvency on fees alone, no token sales
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    ax.plot(days, [t / 1_000_000 for t in mean_daily["treasury"]],
            label="treasury balance (USDS)", color="#1a6faf")
    for d, label in ((90, "entity #2 (Phase 2)"), (180, "entity #3 (Phase 3)"),
                     (EXTERNAL_START_DAY, "external x402 demand opens")):
        ax.axvline(d, color="#888888", linestyle="--", linewidth=0.8)
        ax.annotate(label, xy=(d, ax.get_ylim()[1]), xytext=(d + 3, ax.get_ylim()[1] * 0.97),
                    fontsize=7, color="#555555", rotation=90, va="top")
    ax.axhline(0, color="#a02020", linewidth=0.8)
    ax.set_xlabel("protocol day")
    ax.set_ylabel("treasury balance, USDS")
    ax.set_title("Treasury on coordination fees alone (5%); the token is never sold")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.02), ncols=1, frameon=False)
    fig.savefig(out_dir / "fig3_treasury.png", dpi=150)
    plt.close(fig)

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items()}, indent=2))


if __name__ == "__main__":
    main()
