# ADR-0007 — Integer-canonical wire: the µ¢ convention is protocol, not preference

- **ADR**: 0007
- **Status**: proposed (ratify at Gate 0.4)
- **Date**: 2026-11-04
- **Deciders**: owner (regulator), executing agent (drafter)

## Context
The estate's money layer is already integer-only (µ¢ BigInt convention,
`roshpina/kernel`), and its DEX is a deterministic 38-op kernel — determinism is how
the fleet gets receipts it can re-derive. Floats break both: binary floats make
"settle exactly" unprovable, and JSON float round-trips differ across languages.
Every incident class that starts with "the sum was off by a rounding unit" is
unbuildable on integers.

## Decision
1 µ¢ = 10⁻⁶ USDS; every monetary value is an integer. Dollar literals in code are
written `usds(n)` (impl/dynamis_core/canonical.py) — never hand-converted. Canonical
JSON = sorted keys, tight separators, integers only; `canon()` raises on any float
anywhere in a payload. Hashing is `sha256(canon(x))`; signatures bind to
domain-separated digests (`dyn.*.v1`), so no signature verifies outside its object
type. Shares split by basis points with the remainder absorbed by the last share
(`split_bps`) so parts always sum exactly. The reference implementation is
**stdlib-only**: it must run anywhere the fleet runs with zero dependency risk.

## Consequences
Rates that feel fractional (0.4 DYN per USDS) are integer constants at the µ¢/µDYN
level (`DYN_MU_PER_USDS_MUC = 400`). Display formatting happens at the edge, once.
The constraint is checked mechanically (61 tests include float-rejection and exact-sum
splits), not by review vigilance.

## Exit / Reversal
Relaxing this ADR means abandoning re-derivable settlement — it is effectively
irreversible by design, which is the point.

## Evidence links
`impl/dynamis_core/canonical.py`; `specs/wire.md` §1; `schemas/README.md` (conventions);
test suite: `test_canonical_escrow.py::TestCanonical`.
