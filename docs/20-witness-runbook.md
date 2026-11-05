# 20 — Witness operator runbook (Gate 3.1 onboarding)

The witness band is 7 external operators who seal the chain: every 12 ledger
entries, each witness signs the window's checkpoint; a checkpoint counts only
with **5 of 7 signatures** (BFT ≤ 1 Byzantine). Witness duties, bonds and
slash conditions are specified in `docs/11`; the seal code is
`impl/dyn_ledger.py`; the fraud-catching review band is `impl/dyn_witness.py`.

This runbook is what operator candidate #1 receives (docs/18, Day 3/5).

## What is true today — no promises

Signatures are deterministic domain hashes over `(witness, height,
state_root)` — the documented HSM stand-in (`dyn_ledger._witness_sig`). Real
ed25519 keys generated under two-soul custody and held by the HSM loop are
the **gate-2.1 hardening step**. Roots, quorum counting and tamper detection
are the production path already: the Day 3 dry-run proves they hold and fail
closed — read the measured transcript at
`records/witness-dryrun-2026-11-05.md`, or reproduce it in one command:

```
python3 scripts/witness_dryrun.py
```

Expected verdict: `DRY-RUN GREEN — the seal holds and fails closed`, with
four attacks rejected (substituted entry, forged signature, thin quorum,
edited body — the last via chain integrity, the first three via the
checkpoint itself).

## What an operator can verify offline, today

Anyone — not just witnesses — can check the chain's integrity from a ledger
snapshot alone. Replay every entry through `append` (which recomputes each
hash from its body) and assert the replayed hash equals the recorded one —
an edited body stops the replay at the exact entry:

```
# against any exported checkpoint set + ledger entries:
python3 - <<'PY'
import json, sys
sys.path.insert(0, 'impl')
from dyn_ledger import WorkLedger, verify_checkpoint
rows = json.load(open('LEDGER_ROWS.json'))     # exported entries, in order
cps  = json.load(open('CHECKPOINTS.json'))     # exported seals
led = WorkLedger()
for r in rows:
    e = led.append(day=r["day"], kind=r["kind"], job_id=r["job_id"],
                   agent=r["agent"], **r["body"])
    assert e["hash"] == r["hash"], f"entry {r['seq']} does not replay"
print('chain:', led.verify_chain())
for cp in cps:
    print(cp['height'], verify_checkpoint(cp, led))
PY
```

A checkpoint verifies only if: the height is a real seal point, the state
root and tx root recompute from the snapshot, every signature matches, and
there are at least 5. Anything else fails closed with the reason printed.

## Onboarding checklist (per witness)

1. **Read** `docs/11` (witness duties, bonds, slashing) and `docs/02`
   (two-soul custody — you will generate your signing key this way at 2.1).
2. **Reproduce the dry-run** (command above) and the chain checks on the
   current public snapshot.
3. **Receive the operator pack**: bond terms, the checkpoint-serving schedule
   (every 12 entries), and the challenge-review rotation (`dyn_witness.review`
   — you re-run work in a sandbox, you never trust a verdict).
4. **Register your public key** in `params/` once 2.1 lands; until then your
   witness slot is exercised by the band's stand-in identity (`witness-N`).
5. **Serve**: sign every checkpoint window; a missed window is a liveness
   fault, a wrong signature is a safety fault — both are slashable per the
   bond terms.
6. **Exit**: any time, with the bond's notice period; the band reseals with
   the remaining 6 and a replacement election.

## The line this runbook does not cross

No operator is asked to run unverified code, hold escrowed funds, or trust
any dashboard. The only instruments are: re-run the seal math, re-run the
work, compare digests. Verification is re-runnable, not trusted.
