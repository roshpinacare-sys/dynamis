# ADR-0004 — SOL runs on the kernel ledger; no second accounting database

- **ADR**: 0004
- **Status**: proposed (ratify at Gate 0.4)
- **Date**: 2026-11-04
- **Deciders**: owner (regulator), executing agent (drafter)

## Context
The estate already has two accounting-grade primitives: the `fleet-economy` hash-chain
ledger (append-only, double-balance, `/verify` whole-chain) and the `roshpina` µ¢ BigInt
double-entry kernel with escrow and Merkle audit. Building a separate accounting DB for
business entities would fork truth — the exact disease the fleet's doctrine ("git =
existence", zero simulation) exists to prevent.

## Decision
The Sovereign Operations Layer books everything through the kernel ledger family:
per-entity append-only books (event kinds: accrual, invoice, stream payout, anchor),
integers only, hash-linked, Merkle-anchored via the batch notary (~$0.10). Consolidation
is a read-only view, never a mingling of entity books. DoA enforcement is a policy hook
in the ledger writer, deny-by-default, fail-closed (G28 precedent).

## Consequences
Accounting, settlement, and anchoring share one truth; auditors can verify a whole entity
book with the existing `/verify` pattern. Cost: event-kind schema discipline is mandatory
and changes require ADRs.

## Exit / Reversal
Books are portable JSONL with a published schema; migrating off the kernel is a
re-player, not a rescue.

## Evidence links
`docs/02-sovereign-operations.md` §3; `docs/01-architecture.md` §1; estate audit (gap: no existing accounting DB).
