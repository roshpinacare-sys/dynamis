# ADR-0001 — Chain keys inherit two-soul custody

- **ADR**: 0001
- **Status**: proposed (ratify at Gate 0.4)
- **Date**: 2026-11-04
- **Deciders**: owner (regulator), executing agent (drafter)

## Context
The 2026-10-21 key-rotation incident stranded 12 accounts in a single raidable sandbox;
the census (`ops/custody-census`) now judges key existence chain-side. The estate
still carries dead material: 46 ROT2 rail WIFs, LOST-WITH-SANDBOX accounts
(hcsoldier4/5/6, saos-0001..0009), and an undecided committed vault
(`Saosmartwallet/db/custom.db`, 248 AES-GCM entries).

## Decision
Every DYNAMIS chain key is born two-soul (sealed device vault + cloud secret) and
census-verified before first use. Signing only via HSM `:3057`. Chain keys never reuse
existing persona keys; per-persona isolation (Law 17) applies from genesis.

## Consequences
Key ceremonies become a required, scripted step of Phase 0; nothing ships before 0.2/0.3
close. Rotation is scheduled, not reactive.

## Exit / Reversal
Custody model changes require a new census pass and re-keying — by design expensive.

## Evidence links
`CUSTODY.md` (3 sealed places); founding plan ch. 11 (custody rules); research file §Estate audit.
