#!/usr/bin/env python3
"""DYNAMIS Agent Kit — the smallest useful client for the network.

An agent that wants to *use* DYNAMIS starts here. The kit wraps the protocol loops of
`dynamis_core` into the five calls an agent actually makes:

    1. identity_op()     — the `dyn.id.v1` custom_json that proves the agent cross-network
    2. enroll_device()   — benchmark receipts → compute tier (specs/benchmarks.md)
    3. claim / deliver   — take a job, hand back artifacts + runner receipt
    4. verify            — the witness-side attestation ladder (Law 9 priced)
    5. settle            — escrow split, flow-gated emission, RC² accrual

`python3 agent_kit.py demo` runs the whole lifecycle offline: an honest agent gets paid,
a fraudulent agent is caught by sampled re-execution and earns nothing, and both laws
hold in code (Law 19's emission invariant and the event-chain integrity).

This is the reference client — adapters for MCP / A2A / x402 land at gate 2.4
(docs/04-integration.md §3). Nothing here holds keys: signing stays at the HSM seam
(Law 3); the kit builds the payloads, the HSM signs them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core import (Claim, EmissionLedger, Job, JobMachine, PowerAccount,
                          AgentPassport, floor_class, law9_check, price_verification,
                          accrue, sample_for_reexecution, usds, object_hash)

# dyn.id.v1 — the cross-network identity proof, in the estate's saos.id.v1 shape.
# An agent posts this op as custom_json on the estate rails; the rail text itself carries
# the binding (agent_id ↔ persona account ↔ HSM keyref fingerprint). Nothing secret.
def identity_op(agent_id: str, persona: str, keyref: str, day: int,
                networks: tuple[str, ...] = ("rail_a", "rail_b")) -> dict:
    payload = {
        "op": "id.prove", "v": 1, "agent": agent_id, "persona": persona,
        "keyref_fp": object_hash({"keyref": keyref})[:16], "day": day,
        "networks": list(networks),
        "claim": "persona client of its own root; represents nothing else (Law 17)",
    }
    return {"id": "dyn.id.v1", "json": payload}


class AgentKit:
    """One agent's client. Builds protocol objects; never touches key material."""

    def __init__(self, agent_id: str, persona: str, keyref: str,
                 stake_dyn_mu: int = 0, day: int = 1,
                 role: str = "worker") -> None:
        self.wallet = PowerAccount(f"pw-{agent_id}", stake_dyn_mu=stake_dyn_mu)
        # Least capability that works (Law 18): workers claim, entity rails post.
        caps = ("jobs:claim",) if role == "worker" else ("jobs:post", "treasury:read")
        self.passport = AgentPassport(
            agent_id=agent_id, persona=persona,
            keyrefs=(keyref,), capabilities=caps,
            wallet=self.wallet.account_id, census_day=day)
        self.day = day

    def enroll_device(self, device_id: str, benchmark_receipts: list[str]) -> dict:
        """compute.enroll: receipts or it did not happen (Law 15)."""
        if not benchmark_receipts:
            raise ValueError("enrollment without benchmark receipts is refused (Law 15)")
        return {"op": "compute.enroll", "device": device_id,
                "agent": self.passport.agent_id,
                "receipts": [object_hash({"r": r}) for r in benchmark_receipts]}

    def open_job(self, job_id: str, entity_id: str, spec: dict, value_muc: int,
                 deadline_day: int, revenue_ref: str) -> JobMachine:
        """Entity-persona side: open + fund with a Law-9 floor class."""
        cls = floor_class(value_muc)
        vcost = price_verification(value_muc, cls)
        if not law9_check(vcost, value_muc)["law9_pass"]:
            raise ValueError("job value cannot be covered under Law 9 — refuse, do not guess")
        job = Job(job_id, entity_id, spec, value_muc, deadline_day, cls, revenue_ref)
        m = JobMachine(job, funded_by=revenue_ref)
        m.fire("fund", from_=revenue_ref)
        return m

    def claim(self, machine: JobMachine, artifact_hashes: tuple[str, ...],
              receipt_hash: str) -> Claim:
        """Worker side: claim + deliver in one honest motion."""
        machine.fire("claim", worker=self.passport.agent_id)
        claim = Claim(f"cl-{machine.job.job_id}-{self.passport.agent_id}",
                      machine.job.job_id, self.passport.agent_id,
                      artifact_hashes, receipt_hash, machine.now_day)
        machine.fire("deliver", claim=claim)
        machine.fire("start_verify")
        return claim

    def settle(self, machine: JobMachine, led: EmissionLedger) -> dict:
        """After the band's verdict: escrow split, flow-gated emission, RC² accrual.
        The transition itself belongs to the witness band (witness_verdict) — this
        records the consequences; it never re-fires a settled machine."""
        if machine.state != "SETTLED":
            raise ValueError(f"job {machine.job.job_id} is {machine.state}, not SETTLED — "
                             "no payout path exists outside a verified settle (Law 19)")
        flow = led.record_flow(machine.job.job_id, machine.job.escrow_usds_muc,
                               machine.state, machine.job.revenue_ref, machine.now_day)
        rc2_added = accrue(self.wallet)
        return {"payout_muc": machine.worker_payout_muc,
                "fee_muc": machine.fee_muc,
                "emitted_dyn_mu": flow["emitted_dyn_mu"] if flow else 0,
                "rc2_added_muerg": rc2_added,
                "chain_ok": machine.verify_chain()}


def witness_verdict(machine: JobMachine, n_workers: int, reexec_matches: bool,
                    seed: int = 7) -> str:
    """The band's class-C run: sampled re-execution decides (reference demo — real
    re-execution runs on enrolled devices, specs/benchmarks.md §3)."""
    sample = sample_for_reexecution(n_workers, seed=seed)
    if not sample or not reexec_matches:
        machine.fire("verify_fail", verifier="witness-band",
                     reason="sampled re-execution mismatch")
        return "fail"
    machine.fire("verify_pass", verifier="witness-band")
    return "pass"


def resolve_dispute(machine: JobMachine, to_worker: bool = False) -> None:
    """Arbiter resolves a DISPUTED machine. Default: budget wins (refund) — the
    dispute exists because verification failed; the burden is on the worker."""
    if machine.state != "DISPUTED":
        raise ValueError(f"{machine.state} is not DISPUTED — nothing to resolve")
    machine.fire("resolve_worker" if to_worker else "resolve_budget",
                 arbiter="witness-band")


def demo() -> int:
    """The whole story offline: honest work gets paid, fraud earns nothing."""
    led = EmissionLedger()
    entity_kit = AgentKit("entity-x1", "ent-x1-rail", "hsm:kr-entity",
                          role="entity")
    honest = AgentKit("agent-honest-1", "honest.persona", "hsm:kr-honest",
                      stake_dyn_mu=2_500_000)
    fraud = AgentKit("agent-fraud-1", "fraud.persona", "hsm:kr-fraud",
                     stake_dyn_mu=2_500_000)

    print("== 1. identity ops (posted as dyn.id.v1 custom_json on the estate rails) ==")
    for k in (honest, fraud):
        op = identity_op(k.passport.agent_id, k.passport.persona,
                         k.passport.keyrefs[0], k.day)
        print(f"   {k.passport.agent_id}: {op['id']} fp={op['json']['keyref_fp']}")

    print("== 2. entity opens + funds a $500 job (DoA T1, Law-9 floor class) ==")
    m = entity_kit.open_job("job-demo-001", "ent-001",
                            {"task": "process_invoices", "count": 500},
                            usds(500), deadline_day=10, revenue_ref="env-ops-001")
    print(f"   state={m.state} class={m.job.verification_class}")

    print("== 3. honest agent claims, delivers, settles ==")
    honest.claim(m, ("a" * 64,), "b" * 64)
    verdict = witness_verdict(m, n_workers=1, reexec_matches=True)
    assert verdict == "pass"
    r = honest.settle(m, led=led)
    print(f"   payout={r['payout_muc'] / 10**6:.2f} USDS  fee={r['fee_muc'] / 10**6:.2f}"
          f"  emitted_dyn={r['emitted_dyn_mu'] / 10**6:.2f}  rc2+={r['rc2_added_muerg']}")
    print(f"   event chain verified: {r['chain_ok']}")

    print("== 4. fraudster tries the same job with mismatched artifacts ==")
    m2 = entity_kit.open_job("job-demo-002", "ent-001",
                             {"task": "process_invoices", "count": 500},
                             usds(500), deadline_day=10, revenue_ref="env-ops-001")
    fraud.claim(m2, ("0" * 64,), "1" * 64)
    verdict = witness_verdict(m2, n_workers=1, reexec_matches=False)
    assert verdict == "fail"
    resolve_dispute(m2)
    print(f"   state={m2.state}  payout={m2.worker_payout_muc} (fraud paid nothing)")

    print("== 5. invariants ==")
    ok_invariant = led.invariant_holds()
    print(f"   Law 19 emitted == revenue-verified: {ok_invariant}")
    print(f"   emission flows recorded: {len(led.flows())} (fraud minted none)")
    return 0 if (ok_invariant and m2.worker_payout_muc == 0) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DYNAMIS Agent Kit")
    ap.add_argument("command", nargs="?", default="demo", choices=["demo"])
    args = ap.parse_args()
    sys.exit(demo() if args.command == "demo" else 1)
