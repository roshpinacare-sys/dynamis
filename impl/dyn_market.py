#!/usr/bin/env python3
"""dyn.market.v1 — the standing market: the work loop, running in flow.

A one-shot demo proves a loop works; a market proves an economy does. The daemon
runs the engine (dyn.engine.v1) continuously over protocol days:

  - entities post jobs (varied value → the ladder prices the floor class per job);
  - agents claim and build — behavior is a profile, not a hypothesis:
      honest:  ships a correct artifact, gets paid, accrues RC²;
      fraud:   ships an artifact with a hidden +1¢ error — caught by the evidence
               check, never paid, escrow refunds to the budget, zero emission;
      flaky:   ships a bad artifact first, sees the FAIL evidence, refines in the
               same job folder, then settles — the refine loop is a normal day;
  - every event streams as one JSONL row (the market's audit trail);
  - the day ends with a summary; the same seed replays the same market.

This is the architecture using the engine בשוטף (in flow): not a demo you run once
but a loop you can leave running — the same property craft-anything built into its
engine and benji.org/stageshow teaches for demos: the loop is the product.

  python3 dyn_market.py run --days 14 --seed 7
  python3 dyn_market.py run --days 30 --out market.jsonl

Stdlib only (ADR-0007). Per-job escrow chains live in each job folder; the
market-level view below is the flow stream, with exact µ¢ amounts on the money
rows — the chain-wide ledger that replays it is `dyn_ledger.py` (gate 2.1).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core import PowerAccount, accrue, usds
from dyn_engine import ARTIFACT_INVOICE_PARSER, WorkLoop
from dyn_witness import forge_pass, review as witness_review

MARKET = "dyn.market.v1"

BAD_ARTIFACT = ARTIFACT_INVOICE_PARSER.replace(
    '+ ln["qty"] * ln["unit_cents"]', '+ ln["qty"] * ln["unit_cents"] + 1')

ARTIFACTS = {"good": ARTIFACT_INVOICE_PARSER, "bad": BAD_ARTIFACT}


class Agent:
    """A market participant. Behavior is what it ships, not what it says."""

    def __init__(self, agent_id: str, behavior: str, stake_dyn_mu: int = 2_500_000) -> None:
        self.agent_id = agent_id
        self.behavior = behavior            # honest | fraud | flaky
        self.wallet = PowerAccount(f"pw-{agent_id}", stake_dyn_mu=stake_dyn_mu)
        self.jobs = 0
        self.paid_muc = 0
        self.rc2_muerg = 0

    def first_attempt(self, rng: random.Random) -> str:
        if self.behavior in ("fraud", "forger"):
            return "bad"
        if self.behavior == "flaky" and rng.random() < 0.75:
            return "bad"                    # most days the first build is wrong
        return "good"

    def refines(self) -> bool:
        """Only the flaky agent looks at the FAIL evidence and tries again."""
        return self.behavior == "flaky"


class Market:
    """The loop, left running: days pass, jobs flow, the laws hold every day."""

    def __init__(self, *, seed: int = 7, entity_id: str = "ent-001",
                 revenue_ref: str = "env-ops-001", root: str | Path | None = None,
                 witness: bool = False) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.entity_id = entity_id
        self.revenue_ref = revenue_ref
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="dyn-market-"))
        self.own_root = root is None
        # witness=True admits a forger (forges evidence after a FAIL) and stands
        # the band behind every settlement: sampled re-execution or no payout.
        # Default runs are byte-identical to the pre-band stream.
        self.witness = witness
        self.agents: list[Agent] = []
        for i in range(1, 4):
            self.agents.append(Agent(f"agent-honest-{i}", "honest"))
        self.agents.append(Agent("agent-flaky-1", "flaky"))
        for i in range(1, 3):
            self.agents.append(Agent(f"agent-fraud-{i}", "fraud"))
        if witness:
            self.agents.append(Agent("agent-forger-1", "forger"))
        self.day = 0
        self.stream: list[dict] = []
        self.emitted_dyn_mu = 0
        self.refunded_muc = 0
        self.fees_muc = 0
        self.refined = 0
        self.forged_caught = 0

    # ---------- streaming ----------
    def _emit(self, event: str, **detail) -> None:
        row = {"day": self.day, "event": event, **detail}
        self.stream.append(row)

    # ---------- one protocol day ----------
    def tick(self) -> dict:
        self.day += 1
        n_jobs = self.rng.randint(1, 3)
        workers = self.rng.sample(self.agents, k=min(n_jobs, len(self.agents)))
        day_stats = {"day": self.day, "jobs": 0, "settled": 0, "refunded": 0}
        for i, agent in enumerate(workers):
            job_id = f"job-mkt-{self.day}-{i:02d}"
            value_usds = self.rng.choice((120, 250, 500))
            count = self.rng.choice((100, 250, 500, 900))
            root = self.root / job_id
            loop = WorkLoop(root)
            loop.job_new(job_id=job_id, entity_id=self.entity_id,
                         revenue_ref=self.revenue_ref, value_muc=usds(value_usds),
                         deadline_day=self.day + 7, seed=1000 + self.rng.randint(0, 8999),
                         count=count, currencies=("USD", "EUR"), buyer_count=20,
                         day=self.day)
            self._emit("open", job=job_id, agent=agent.agent_id,
                       value_usds=value_usds, value_muc=usds(value_usds),
                       count=count,
                       cls=loop.log["job"]["verification_class"])
            day_stats["jobs"] += 1
            agent.jobs += 1

            art = root / "incoming.py"
            art.write_text(ARTIFACTS[agent.first_attempt(self.rng)])
            loop.work(art)
            self._emit("work", job=job_id, agent=agent.agent_id,
                       sha256=loop.log["artifact"]["sha256"][:16])

            res = loop.check(day=self.day)
            if res["overall"] == "PASS":
                self._emit("check", job=job_id, agent=agent.agent_id, overall="PASS")
            else:
                self._emit("check", job=job_id, agent=agent.agent_id, overall="FAIL")
                if agent.refines():
                    self.refined += 1
                    self._emit("refine", job=job_id, agent=agent.agent_id,
                               note="FAIL evidence read; same folder, new build")
                    art.write_text(ARTIFACTS["good"])
                    loop.work(art)
                    self._emit("work", job=job_id, agent=agent.agent_id,
                               sha256=loop.log["artifact"]["sha256"][:16])
                    res = loop.check(day=self.day)
                    self._emit("check", job=job_id, agent=agent.agent_id,
                               overall=res["overall"])

            if res["overall"] != "PASS" and self.witness \
                    and agent.behavior == "forger" and self.rng.random() < 0.6:
                # the attack the band exists for: a failed build made to look
                # paid-for — evidence records edited, worklog status flipped
                forge_pass(root)
                loop = WorkLoop(root)          # reload: the folder changed on disk
                res = {"overall": "PASS"}
                self._emit("check", job=job_id, agent=agent.agent_id,
                           overall="PASS", note="presented by worker (forged)")

            if res["overall"] == "PASS":
                forged = False
                if self.witness:
                    cls = loop.log["job"]["verification_class"]
                    v = witness_review(root, day=self.day, cls=cls)
                    self._emit("witness", job=job_id, agent=agent.agent_id,
                               cls=cls, sampled=v["sampled"],
                               leader=v["leader"], matches=v["matches"],
                               forged=v["forged"])
                    forged = v["forged"]
                if forged:
                    loop = WorkLoop(root)      # reload: overrule rewrote evidence
                    back = loop.refund(day=self.day, worker_id=agent.agent_id)
                    self.refunded_muc += back["escrow_back_muc"]
                    day_stats["refunded"] += 1
                    self.forged_caught += 1
                    self._emit("refund", job=job_id, agent=agent.agent_id,
                               escrow_back_usds=back["escrow_back_muc"] // 1_000_000,
                               escrow_back_muc=back["escrow_back_muc"],
                               emitted_dyn_mu=0,
                               reason="forged evidence caught by sampled re-execution")
                else:
                    out = loop.settle(day=self.day, worker_id=agent.agent_id,
                                      persona=f"{agent.agent_id}.persona",
                                      keyref=f"hsm:kr-{agent.agent_id}")
                    self.emitted_dyn_mu += out["emitted_dyn_mu"]
                    self.fees_muc += out["fee_muc"]
                    agent.paid_muc += out["payout_muc"]
                    agent.rc2_muerg += accrue(agent.wallet, days=1)
                    day_stats["settled"] += 1
                    self._emit("settle", job=job_id, agent=agent.agent_id,
                               payout_usds=out["payout_muc"] // 1_000_000,
                               fee_usds=out["fee_muc"] // 1_000_000,
                               payout_muc=out["payout_muc"], fee_muc=out["fee_muc"],
                               emitted_dyn_mu=out["emitted_dyn_mu"],
                               chain_ok=out["chain_ok"])
            else:
                back = loop.refund(day=self.day, worker_id=agent.agent_id)
                self.refunded_muc += back["escrow_back_muc"]
                day_stats["refunded"] += 1
                self._emit("refund", job=job_id, agent=agent.agent_id,
                           escrow_back_usds=back["escrow_back_muc"] // 1_000_000,
                           escrow_back_muc=back["escrow_back_muc"],
                           emitted_dyn_mu=0)
        return day_stats

    # ---------- the run ----------
    def run(self, days: int, out: str | Path | None = None) -> dict:
        for _ in range(days):
            self.tick()
        honest = [a for a in self.agents if a.behavior == "honest"]
        fraud = [a for a in self.agents if a.behavior == "fraud"]
        settled = sum(1 for r in self.stream if r["event"] == "settle")
        refunds = sum(1 for r in self.stream if r["event"] == "refund")
        summary = {
            "market": MARKET, "seed": self.seed, "days": days,
            "jobs_opened": sum(1 for r in self.stream if r["event"] == "open"),
            "settled": settled, "refunded": refunds, "refined": self.refined,
            "witnessed": sum(1 for r in self.stream if r["event"] == "witness"),
            "forged_caught": self.forged_caught,
            "emitted_dyn_mu": self.emitted_dyn_mu,
            "fees_usds": self.fees_muc // 1_000_000,
            "escrow_refunded_usds": self.refunded_muc // 1_000_000,
            "agents": {a.agent_id: {"behavior": a.behavior, "jobs": a.jobs,
                                    "paid_usds": a.paid_muc // 1_000_000,
                                    "rc2_muerg": a.rc2_muerg}
                       for a in self.agents},
            "laws": {
                "law19_fraud_never_paid": all(a.paid_muc == 0 for a in fraud),
                "law19_refund_emits_nothing": all(
                    r["emitted_dyn_mu"] == 0 for r in self.stream if r["event"] == "refund"),
                "no_payout_without_pass": all(
                    r["emitted_dyn_mu"] > 0 for r in self.stream if r["event"] == "settle"),
                "forged_evidence_never_paid": self.forged_caught == sum(
                    1 for r in self.stream if r["event"] == "witness" and r["forged"]),
            },
        }
        if out:
            with open(out, "w") as f:
                for row in self.stream:
                    f.write(json.dumps(row, sort_keys=True) + "\n")
                f.write(json.dumps({"summary": summary}, sort_keys=True) + "\n")
        return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dyn_market",
                                 description="DYNAMIS standing market (dyn.market.v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default=None, help="write the JSONL stream here")
    a = ap.parse_args(argv)

    m = Market(seed=a.seed)
    summary = m.run(a.days, out=a.out)
    print(f"market {MARKET} — {summary['days']} days, seed {summary['seed']}")
    print(f"  jobs {summary['jobs_opened']}  settled {summary['settled']}  "
          f"refunded {summary['refunded']}  refined {summary['refined']}")
    print(f"  emitted {summary['emitted_dyn_mu'] // 1_000_000} DYN  "
          f"fees {summary['fees_usds']} USDS  refunded {summary['escrow_refunded_usds']} USDS")
    for aid, s in summary["agents"].items():
        print(f"  {aid:<16} {s['behavior']:<6} jobs {s['jobs']:<3} "
              f"paid {s['paid_usds']:<5} rc2 {s['rc2_muerg']}")
    print(f"  laws: " + ", ".join(f"{k}={v}" for k, v in summary["laws"].items()))
    if a.out:
        print(f"  stream: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
