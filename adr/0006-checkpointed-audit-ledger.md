# ADR-0006 — Checkpointed audit ledger at genesis, not a from-scratch L1

- **ADR**: 0006
- **Status**: proposed (ratify at Gate 0.4)
- **Date**: 2026-11-04
- **Deciders**: owner (regulator), executing agent (drafter)

## Context
DYNAMIS needs shared state (jobs, escrows, receipts, witnesses) but does not need to
launch a full proof-of-stake chain on day one. The estate already operates: a
hash-chain economy ledger with whole-chain verification (`:3016`), 3-second DEX blocks
sealed every 12 (the pulse pattern), batched anchoring (~$0.10/batch on ETH, free
custom_json notary on the estate rails), and a witness selection model (VRF over measured
custody). Building a novel BFT network first would spend the roadmap's riskiest weeks
on infrastructure nobody is paying for yet.

## Decision
Genesis era: DYNAMIS is a **checkpointed audit ledger**. State = event chains + receipt
chains + accounts; a 7-witness band seals checkpoints (3 s blocks, seal every 12,
finality 5-of-7, minority fork halts fail-closed); epoch seals anchor to the estate's
existing rails. Ops ride `dyn.v1` custom_json (specs/wire.md §2). Progression to a
full sovereign consensus network is a Phase-3+ ADR that must cite measured demand
(settled external flow), not ambition.

## Consequences
Liveness depends on band health until external witnesses land (gate 3.1) — stated as a
residual risk in docs/07 §8. Throughput is bounded by the seal cadence, which is fine
for job-shaped (not HFT-shaped) load. No new consensus code has to be trusted before
it has earned trust.

## Exit / Reversal
The ledger is exportable by construction: event chains re-derive from canonical bytes
anywhere (ADR-0007). Migrating to another chain or a full L1 re-anchors the same roots.

## Evidence links
`specs/wire.md` §2, §4; `impl/dynamis_core/escrow.py` (event chains);
`docs/01-architecture.md` §1 (existing estate machinery); docs/07 §6 (witness threats).
