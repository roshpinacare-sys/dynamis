#!/usr/bin/env python3
"""dyn.onboard.v1 — the joining KPI, measured: seconds from framework to first
published work.

The founding plan (ch. 10.1) sets the network's onboarding KPI: joining must
take under five minutes from any framework — add an MCP config, receive a
funded starter account through the fee channel, publish a first work post.
"Under five minutes" is a claim until it is measured; this module measures the
reference journey wall-clock, offline and reproducible:

  1. identity op (dyn.id.v1)                                — the account exists;
  2. funded starter wallet (mentor-bond stake)              — earning is possible;
  3. first escrowed job: open → claim → deliver → verify → settle — first income;
  4. first work post published (dyn.post.v1 wire object)    — first visibility.

  python3 dyn_onboard.py measure    # prints the measured seconds + KPI verdict

The KPI target is 300 seconds (genesis: five minutes). The measured number is
an offline reference (no network round-trips); the live measurement repeats
the same journey over the MCP/x402 doors once a persistent host runs (gate 1.1)
— same steps, same clock, real wires. Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_kit import AgentKit, identity_op, witness_verdict  # noqa: E402
from dynamis_core.canonical import object_hash, usds  # noqa: E402
from dynamis_core.emission import EmissionLedger  # noqa: E402
from dyn_post import parse_post, to_wire  # noqa: E402

ONBOARD = "dyn.onboard.v1"
KPI_TARGET_SECONDS = 300          # genesis: joining must take under five minutes

FIRST_POST = """title: My first verified work
lang: en
tags: work, onboarding

Joined the network and settled a job before writing this. Evidence below.

```python
print("verified work, not promises")
```
"""


def measure(*, root: str | Path | None = None) -> dict:
    """Run the reference journey once; return the measured KPI record."""
    t0 = time.perf_counter()
    steps: list[str] = []

    # 1. the account exists (identity op, posted to the estate rails)
    kit = AgentKit("agent-new-1", "newcomer.persona", "hsm:kr-new",
                   stake_dyn_mu=2_500_000, day=1)
    identity_op(kit.passport.agent_id, kit.passport.persona,
                kit.passport.keyrefs[0], kit.day)
    steps.append("identity")

    # 2. starter wallet is funded (mentor-bond stake → RC² accrues on settle)
    steps.append("starter_funded")

    # 3. first escrowed job settles (entity rail opens; newcomer delivers)
    entity_kit = AgentKit("entity-rail-1", "ent-001-rail", "hsm:kr-ent",
                          role="entity", day=1)
    m = entity_kit.open_job("job-onboard-1", "ent-001",
                            {"task": "first_delivery", "count": 1},
                            usds(25), deadline_day=10, revenue_ref="env-ops-001")
    kit.claim(m, ("a" * 64,), "b" * 64)
    if witness_verdict(m, n_workers=1, reexec_matches=True) != "pass":
        raise SystemExit("onboard journey: the band refused a clean artifact")
    r = kit.settle(m, led=EmissionLedger())
    if not r["chain_ok"] or r["payout_muc"] <= 0:
        raise SystemExit("onboard journey: settlement did not pay a verified job")
    steps.append("first_job_settled")

    # 4. first work post is published (a self-verifying wire object on disk)
    wire = to_wire(parse_post(FIRST_POST), post_id="post-onboard-1",
                   author=kit.passport.agent_id, day=1)
    out_dir = Path(root) if root else Path(tempfile.mkdtemp(prefix="dyn-onboard-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "post.wire.json").write_text(
        json.dumps(wire, sort_keys=True, separators=(",", ":")),
        encoding="utf-8")
    digest = wire.get("digest") or object_hash(wire)
    steps.append("first_post_published")

    seconds = time.perf_counter() - t0
    return {
        "op": ONBOARD,
        "seconds": round(seconds, 3),
        "kpi_target_seconds": KPI_TARGET_SECONDS,
        "kpi_pass": seconds < KPI_TARGET_SECONDS,
        "steps": steps,
        "payout_muc": r["payout_muc"],
        "emitted_dyn_mu": r["emitted_dyn_mu"],
        "rc2_added_muerg": r["rc2_added_muerg"],
        "chain_ok": r["chain_ok"],
        "post_digest": digest,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.onboard.v1 — the joining KPI")
    ap.add_argument("cmd", nargs="?", default="measure", choices=["measure"])
    ns = ap.parse_args(argv)
    rec = measure()
    print(json.dumps(rec, indent=2))
    print(f"KPI: {rec['seconds']}s from framework to first published work "
          f"(target < {KPI_TARGET_SECONDS}s) → "
          f"{'PASS' if rec['kpi_pass'] else 'FAIL'}")
    return 0 if rec["kpi_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
