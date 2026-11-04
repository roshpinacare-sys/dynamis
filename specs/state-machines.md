# State machines — formal spec of the job lifecycle

The executable half is `impl/dynamis_core/escrow.py` (fail-closed `TRANSITIONS` dict,
hash-chained event log, 61 tests). This document is the normative statement; the code
and this file are kept in lockstep — a change to either without the other fails review.

## 1. States

```
OPEN ──fund──▶ FUNDED ──claim──▶ CLAIMED ──deliver──▶ DELIVERED ──start_verify──▶ VERIFYING
 │               │timeout/cancel │timeout      │dispute/timeout        │pass            │dispute
 │               ▼               ▼             ▼                       ▼                ▼
 └─cancel──▶ REFUNDED ◀──────────┘          DISPUTED ◀──verify_fail──────┘          DISPUTED
                ▲                            │resolve_worker                    │
                └─────────resolve_budget─────┴──────────────▶ SETTLED ◀──────────┘
```

Terminal: `SETTLED`, `REFUNDED`. Terminal states are absorbing — no event is legal in
them, ever (tested: `test_terminal_state_is_absorbing`).

## 2. Transition table (complete — anything not listed is illegal)

| From | Event | To | Guard | Effect |
|---|---|---|---|---|
| OPEN | fund | FUNDED | escrow > 0; DoA T1 passed | escrow locked |
| OPEN | cancel | REFUNDED | — | nothing to refund |
| FUNDED | claim | CLAIMED | worker ≠ funder (self-dealing blocked) | claim recorded |
| FUNDED | timeout | REFUNDED | `now_day > deadline_day` | escrow returns, fee 0 |
| FUNDED | cancel | REFUNDED | budget withdraws | escrow returns, fee 0 |
| CLAIMED | deliver | DELIVERED | claim.schema valid; receipt verifies | artifacts hash-stamped |
| CLAIMED | timeout | REFUNDED | deadline | escrow returns, fee 0 |
| DELIVERED | start_verify | VERIFYING | — | ladder run opens |
| DELIVERED | dispute | DISPUTED | challenger ≠ worker | dispute window opens |
| DELIVERED | timeout | REFUNDED | deadline | verifier stall must not trap worker funds |
| VERIFYING | verify_pass | SETTLED | independent verifier named; ≥ floor class ran | fee split; emission proposed |
| VERIFYING | verify_fail | DISPUTED | re-execution/benchmark mismatch | bond burn recorded |
| VERIFYING | dispute | DISPUTED | challenger joins mid-verification | dispute window opens |
| VERIFYING | timeout | REFUNDED | deadline | same anti-trap rule |
| DISPUTED | resolve_worker | SETTLED | named arbiter (witness band) | fee split; emission proposed |
| DISPUTED | resolve_budget | REFUNDED | named arbiter | escrow returns; fraud bonds burn |

## 3. Invariants (every one is enforced in code and tested)

- **I1 (absorbing terminals)** — no event leaves `SETTLED`/`REFUNDED`.
- **I2 (deadline honesty)** — any non-timeout event after `deadline_day` raises;
  a stale job must refund, never settle. `tick()` refuses to move time backwards.
- **I3 (self-dealing blocked)** — the funder of an escrow can never claim it.
- **I4 (no settlement without independent verification)** — `verify_pass` requires a
  named verifier distinct from the worker; self-reported evaluation is rejected at the
  transition level (the ACP pattern, hardened).
- **I5 (refund takes no fee)** — every path into `REFUNDED` leaves `fee_muc == 0`;
  the coordination fee exists only where verified work settled.
- **I6 (dispute needs an arbiter)** — resolution events require a named arbiter.
- **I7 (tamper-evident history)** — `verify_chain()` re-derives the event hash chain;
  any mutation of past events breaks every subsequent link.
- **I8 (emission strictly behind settlement)** — `EmissionLedger.record_flow` accepts
  only `state == "SETTLED"` with a `revenue_ref`; duplicates rejected; the running
  invariant `emitted == revenue × rate` holds mathematically (gate 2.2's dashboard line).

## 4. Timeouts and liveness

| Timer | Default | On fire |
|---|---|---|
| job deadline | per job spec (day-granular) | `timeout()` → REFUNDED |
| claim execution | min(3 days, deadline) | claim released to market again (re-claim event, v2) |
| verification | 24 h after DELIVERED | REFUNDED (anti-trap) — verifier band is slashed for miss |
| dispute window | 72 h from DELIVERED | auto-resolve to arbiter of record |

Time is the protocol day (wire.md §5); one clock, no drift between scheduling subsystems.

## 5. Why this shape

- ACP's escrow→deliver→evaluate→settle shape is adopted; self-reported evaluation is
  replaced by the verification transition (I4) — that is the differentiator.
- Steem's failure mode (payout by narrative vote) cannot be expressed: there is no
  transition that moves value without passing through `VERIFYING` (or an arbiter).
- Refund-biased defaults: every stall path returns funds. The state machine can lose
  liveness temporarily; it can never lose custody — custody errors are the
  2026-10-21 lesson, and the machine is built so that class of error is unrepresentable.
