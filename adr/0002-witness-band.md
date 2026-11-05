# ADR-0002 — Witness band 7+14 with VRF over measured custody

- **ADR**: 0002
- **Status**: accepted (owner directive 2026-11-05: the owner approved the plan and ordered full execution)
- **Date**: 2026-11-04
- **Deciders**: owner (regulator), executing agent (drafter)

## Context
THE WEAVE law 15 demanded witnesses "derived deterministically" from measured custody —
the next generation of the estate's derivative law. Frontier check (2026-11): escrowed
agent commerce and verifiable inference are mainstreaming (ACP, x402, TEE ~5% overhead),
so consensus duties can be priced and staffed realistically.

## Decision
Witness band of 7 active + 14 standby, selected by VRF over census-verified custody
score + benchmark history. Duties: checkpoint signing, compute price feed (median of
sampled DePIN spot prices + fleet-measured cost), challenge verification, census judging.
Bond-based slashing; missed duty promotes the standby.

## Consequences
No self-declared capacity anywhere in consensus. The price feed gives ERG a live,
manipulation-resistant anchor and gives SOL a defensible compute-price oracle.

## Exit / Reversal
Band size and duty list are genesis parameters; changing them is a T3 decision
(regulator veto) with an ADR.

## Evidence links
`docs/03-protocol.md` §2; `params/genesis.yaml#witnesses`; research file §6–7.
