# ADR-0008 — DYN substrate: native to the estate stack at every layer; own-chain clone for the public work-ledger

- **ADR**: 0008
- **Status**: accepted (owner directive, 2026-11-04: "run the project on my network's own
  token; a clone of another blockchain is acceptable; maximize the benefit to the
  sovereign autonomous architecture")
- **Date**: 2026-11-04
- **Deciders**: owner (regulator, by directive), executing agent (drafter)

## Context
The owner asked whether DYNAMIS can run **on top of a token of their own network**
rather than launching on someone else's chain — and stated that a clone of another
blockchain is acceptable if that serves the sovereign architecture better. The estate
already operates the required machinery: the `fleet-economy` hash-chain ledger
(`:3016`, append-only, whole-chain `/verify`) as the accounting root, the DEX kernel
with an estate custom_json fuel rail, and anchoring rails (estate notary, batched ETH
notary) for external verifiability. Law 16 (root sovereignty) and Law 21 (exit is a
right) forbid making the root's value layer dependent on infrastructure it does not
control.

## Options considered
1. **Launch DYN on an external L1** (an existing public chain as the token's home).
   Rejected: value records and validators fall under foreign governance; exit is no
   longer one working day; fees and uptime are someone else's risk. This is the one
   option Law 21 forbids outright for value.
2. **Own chain derived from a proven codebase** (a proven open-ledger lineage —
   code the estate already operates at production scale via the estate's flagship deployment).
   Accepted as the **public work-ledger** (gate 2.1+): the estate controls validators,
   upgrade cadence, and economics; the lineage is battle-tested and matches the social
   rail already in use.
3. **Native instrument on the estate ledger** (`:3016` family).
   Accepted as the **root-side layer of record from day one**: DYN positions and USDS
   settlement for the inner economy are booked as instrument entries on the kernel
   ledger — integer-only, hash-linked, Merkle-anchored — exactly like every other
   estate asset (ADR-0004 discipline: no second accounting database).

## Decision
DYN is **native to the estate-controlled stack at every layer — no third-party L1 ever
holds value**:

- **Root / inner economy (now)**: DYN exists as a flow-gated instrument on the kernel
  ledger (`:3016`); USDS is the settlement unit; escrow is the roshpina kernel pattern.
- **Public work-ledger (gate 2.1+)**: the DYNAMIS chain is the estate's **own chain
  core**, derived from the open-ledger codebase the estate already runs — a clone by
  lineage, sovereign by control. Emission is computed there from verified flows
  (Law 19) and mirrored back as instrument entries.
- **External verifiability (now)**: anchoring via the existing estate notary and batched
  ETH notary rails — proofs on foreign chains, never value on foreign chains.
- **Bridges**: the only cross-chain artifacts are the ERC-8004 mirror (identity, not
  value) and notary digests. No token bridge is planned; a token bridge would be a
  Law-21 violation by construction.

## Consequences
The network's value layer is a superset of machinery the fleet already measures and
operates, so the bring-up (`docs/09-live-bring-up.md`) needs no new trust assumptions.
The emission ledger and the kernel ledger share one truth per entity. Cost: the public
chain inherits open-ledger governance pathologies — which the canon (evidence-window,
witness band, work verification) exists to fix, and which are mitigated at genesis
rather than patched later.

## Exit / Reversal
Instrument entries are portable JSONL with a published schema (same property as
ADR-0004). If the own-chain path is ever abandoned, the layer of record remains the
kernel ledger; the public chain can be re-genesis'd from anchored checkpoints without
touching the root.

## Evidence links
`params/genesis.yaml#substrate`; `docs/03-protocol.md` §tokens; `docs/09-live-bring-up.md`
§1–2; `adr/0004-kernel-ledger.md`; CANON Laws 16, 19, 21; owner directive 2026-11-04.
