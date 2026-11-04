# Wire schemas — machine-checkable contracts for every protocol object

JSON Schema draft 2020-12. These are the wire truth; `impl/dynamis_core/objects.py`
is the executable half of the same contracts, and `params/genesis.yaml` holds the
canonical numbers. A payload that fails its schema never enters a state machine.

| Schema | Object | Validated by |
|---|---|---|
| [`job.schema.json`](job.schema.json) | market job (docs/03 §1) | escrow `JobMachine`, gates 1.5 / 2.1 |
| [`claim.schema.json`](claim.schema.json) | worker deliverable | `DELIVERED` transition |
| [`receipt.schema.json`](receipt.schema.json) | runner `:3020` receipt, hash-chained | attestation ladder class ≥ B |
| [`eval.schema.json`](eval.schema.json) | paid evaluator verdict | eval market (gate 3.2) |
| [`agent.schema.json`](agent.schema.json) | agent passport + directory record | Agent Directory (docs/04 §4) |
| [`entity.schema.json`](entity.schema.json) | SOL org-as-contract (Law 20, docs/02 §1) | gate 0.5 |
| [`doa.schema.json`](doa.schema.json) | delegation-of-authority matrix | policy engine (impl) |

Conventions (ADR-0007):

- Money fields end in `_muc`: integer µ¢, 1 µ¢ = 10⁻⁶ USDS. Floats are invalid everywhere.
- All identifiers match `^[a-z0-9][a-z0-9-]{2,63}$`.
- Every hash field is lowercase sha256 hex (64 chars).
- Times are protocol day numbers (integer) or ISO-8601 UTC strings for off-chain fields.

Validation in CI (gate tooling, Phase 0): `python -m jsonschema` or the stdlib checker
in `impl/tests/` once a dependency-free validator lands. Nothing ships that cannot be
checked mechanically — a schema nobody runs is a doc, not a gate.
