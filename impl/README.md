# impl/ — the executable reference of the DYNAMIS loops

Stdlib-only Python (zero dependencies, by ADR-0007: the reference must run anywhere the
fleet runs, with no supply-chain surface). Every module is the executable half of a
section in `docs/03-protocol.md`; every law it enforces is cited in its docstring.

| Module | Implements | Laws enforced in code |
|---|---|---|
| `canonical.py` | canonical JSON, integer money (`usds()`), domain-separated hashing, exact bps splits | Law 4, ADR-0007 |
| `objects.py` | Job, Claim, Eval, AgentPassport, PowerAccount — validated at construction | Laws 3, 4, 17, 18 |
| `escrow.py` | the job state machine, fail-closed transitions, hash-chained event log, deadline refunds | Laws 4, 19 |
| `policy.py` | DoA engine (T0–T3+X), budget envelopes, rail caps, runway floor | Laws 20, 9 |
| `ladder.py` | attestation classes A–E, fraud-economics math, `floor_class`, `law9_check`, sampled re-execution | Law 9 |
| `pricefeed.py` | witness medianizer with outlier flags (bond-burn candidates) | Laws 8, 15 |
| `rc2.py` | stake-accrued inference credits: accrue, spend (deny-by-default), integer stake factor | genesis#rc2 |
| `brier.py` | evaluator Brier scores, bond burn, calibration buckets, ECE | Laws 8, 13 |
| `antiherd.py` | mulberry32 (bit-exact with the fleet), `mulberry32(day\|account)` schedules, caps + gaps | Laws 13, 14 |
| `emission.py` | flow-gated emission ledger; refuses to mint against anything but a settled flow | Law 19 |

## Run

```bash
cd impl
python -m unittest discover -s tests -v     # 231 tests, the executable acceptance checks
```

The end-to-end test (`tests/test_end_to_end.py`) is the founding plan in miniature:
one business job from entity budget → escrow → independent verification → settlement →
flow-gated emission → RC² accrual, plus the seeded-fraud drill where the fraudster is
caught, paid nothing, and mints nothing.

## Conventions

- Money is always `usds(N)` µ¢ (1 µ¢ = 10⁻⁶ USDS). Never hand-write dollar literals.
- Any float anywhere in a canonical payload raises — integers only, ever (ADR-0007).
- New canonical numbers go into `params/genesis.yaml` first, then here as named constants.
