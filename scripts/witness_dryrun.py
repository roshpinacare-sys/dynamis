#!/usr/bin/env python3
"""witness_dryrun.py — the Day 3 dry-run, on the real seal code (docs/18).

docs/18 Day 3 says: *simulate the 5-of-7 checkpoint seal with the real keys
on a scratch ledger*. The seal code in dyn_ledger.py is the production path —
this script drives it end to end and writes the measured transcript to
records/:

  1. build a scratch WorkLedger with real job flows (post → work → settle);
  2. seal every full 12-entry window with 7 witness signatures;
  3. verify every checkpoint (roots recompute, sigs match, BFT ≥ 5);
  4. attack it three ways — a tampered entry, a forged signature, and a
     4-of-7 quorum — each must fail closed;
  5. run the Law 19 invariant over the same scratch ledger.

The signatures are the documented HSM stand-ins (deterministic domain hashes);
real ed25519-via-HSM keys are the gate-2.1 hardening step. Everything else —
roots, quorum, tamper detection — is the code that will carry the live band.

  python3 scripts/witness_dryrun.py                # transcript to stdout
  python3 scripts/witness_dryrun.py --out records/witness-dryrun.md
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))

from dyn_ledger import (BFT_THRESHOLD, SEAL_EVERY, WITNESSES,  # noqa: E402
                        WorkLedger, verify_checkpoint)

DAY = 1


def scratch_ledger(jobs: int = 10) -> WorkLedger:
    """A real job flow per job: post → work → check → settle (Law 19 exact)."""
    led = WorkLedger()
    for j in range(jobs):
        job = f"dry-{j:03d}"
        led.append(day=DAY, kind="post", job_id=job, agent="client",
                   spec_hash=f"spec-{j}")
        led.append(day=DAY, kind="work", job_id=job, agent=f"worker-{j % 3}",
                   artifact_hash=f"art-{j}")
        led.append(day=DAY, kind="check", job_id=job, agent="engine",
                   verdict="PASS")
        price_muc = 25_000_000 + j * 1_000_000
        led.append(day=DAY, kind="settle", job_id=job, agent="escrow",
                   payout_muc=price_muc - price_muc // 20,
                   fee_muc=price_muc // 20,
                   emitted_dyn_mu=(price_muc) * 400)
    return led


def _attack_substitute(led: WorkLedger, cps: list[dict]) -> dict:
    """A different entry occupying slot 3 (its hash differs from what was
    sealed) → the state root must break."""
    bad = copy.deepcopy(led.entries)
    bad[3]["hash"] = "f" * 64
    tampered = WorkLedger()
    tampered.entries = bad
    return verify_checkpoint(cps[0], tampered)


def _attack_body_edit(led: WorkLedger) -> dict:
    """Edit a settled payout in place, hash left stale → chain integrity
    (recompute every hash) must flag the exact entry."""
    bad = copy.deepcopy(led.entries)
    bad[3]["body"]["payout_muc"] += 1
    tampered = WorkLedger()
    tampered.entries = bad
    return tampered.verify_chain()


def _attack_forge(led: WorkLedger, cps: list[dict]) -> dict:
    """A signature not produced by the seal function → must be rejected."""
    forged = copy.deepcopy(cps[0])
    forged["witness_sigs"][0]["s"] = "0" * 64
    return verify_checkpoint(forged, led)


def _attack_quorum(led: WorkLedger, cps: list[dict]) -> dict:
    """Only 4 of 7 sigs — below BFT_THRESHOLD → must be rejected."""
    thin = copy.deepcopy(cps[0])
    thin["witness_sigs"] = thin["witness_sigs"][:BFT_THRESHOLD - 1]
    return verify_checkpoint(thin, led)


def run(jobs: int = 10) -> list[str]:
    led = scratch_ledger(jobs)
    cps = led.all_checkpoints(day=DAY)
    out: list[str] = []
    out.append(f"# Witness dry-run — 5-of-7 checkpoint seal, on the real seal code")
    out.append("")
    out.append(f"Scratch ledger: {len(led.entries)} entries over {jobs} job "
               f"flows (post → work → check → settle); seal every "
               f"{SEAL_EVERY} entries; BFT threshold {BFT_THRESHOLD} of "
               f"{len(WITNESSES)} witnesses. Signatures are the documented "
               f"HSM stand-ins; roots, quorum and tamper detection are the "
               f"production path (impl/dyn_ledger.py).")
    out.append("")
    chain = led.verify_chain()
    out.append(f"- chain integrity: ok={chain['ok']} "
               f"depth={chain['depth']} (every hash recomputed and linked)")
    for cp in cps:
        v = verify_checkpoint(cp, led)
        out.append(f"- checkpoint @{cp['height']:>3}: state_root "
                   f"{cp['state_root'][:16]}…, tx_root "
                   f"{cp['tx_root'][:16]}…, {len(cp['witness_sigs'])} sigs "
                   f"→ {'OK' if v['ok'] else 'FAIL: ' + str(v['why'])}")
    out.append("")
    out.append("Fail-closed attacks (each must be rejected):")
    attacks = (("substituted entry (different hash at slot 3 — the checkpoint "
                "commits to entry hashes)", _attack_substitute(led, cps)),
               ("forged signature (hex zeros)", _attack_forge(led, cps)),
               (f"thin quorum ({BFT_THRESHOLD - 1} of {len(WITNESSES)} sigs)",
                _attack_quorum(led, cps)))
    for name, v in attacks:
        out.append(f"- {name} → {'REJECTED' if not v['ok'] else '!! ACCEPTED — SEVERE'}"
                   f"{' (' + str(v['why']) + ')' if v.get('why') else ''}")
    body = _attack_body_edit(led)
    out.append(f"- edited payout body (stale hash — caught by chain integrity, "
               f"not the checkpoint) → "
               f"{'REJECTED' if not body['ok'] else '!! ACCEPTED — SEVERE'} "
               f"(first_bad entry: {body['first_bad']})")
    inv = led.invariant()
    out.append("")
    out.append(f"- Law 19 on the scratch ledger: settled {inv['settled_usds_muc']:,} µ¢ "
               f"→ emitted {inv['emitted_dyn_mu']:,} DYN-µ at rate {inv['rate']}: "
               f"equal={inv['emitted_eq_revenue']}, refunds emit nothing="
               f"{inv['refund_emits_nothing']}")
    ok = (chain["ok"] and all(verify_checkpoint(c, led)["ok"] for c in cps)
          and all(not v["ok"] for _, v in attacks) and not body["ok"]
          and inv["emitted_eq_revenue"])
    out.append("")
    out.append(f"Verdict: {'DRY-RUN GREEN — the seal holds and fails closed' if ok else 'DRY-RUN RED — investigate'}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Day 3 witness dry-run")
    ap.add_argument("--jobs", type=int, default=10)
    ap.add_argument("--out", default="-", help="transcript path ('-' = stdout)")
    ns = ap.parse_args(argv)
    lines = run(ns.jobs)
    text = "\n".join(lines) + "\n"
    if ns.out == "-":
        print(text, end="")
    else:
        p = Path(ns.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"transcript written: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
