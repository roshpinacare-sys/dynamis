# ADR-0005 — Sim-first development: the simulator is the falsifiable model

- **ADR**: 0005
- **Status**: proposed (ratify at Gate 0.4)
- **Date**: 2026-11-04
- **Deciders**: owner (regulator), executing agent (drafter)

## Context
The estate's own audit lesson (FLEET-AUDIT-2026-11-01: machinery 60, economics 0) is
that this fleet builds machinery faster than it builds economies. Protocol economics —
emission rates, verification budgets, slashing multiples — cannot be argued into
correctness; Steem argued its inflation pool into a decade of defense.

## Decision
Every change to emission, verification, pricing, or market mechanics follows the order
**simulate → reference-implement → gate**. `sim/simulate_economy.py` is the canonical
falsifiable model: deterministic seeds, published parameters, three provable lines
(Law-19 invariant exact, Law-9 margin ≥ 0 on every seed, treasury solvent on fees
alone). A change that fails any line in any seed is rejected at design time, not at
mainnet time. The sim's parameters are labeled estimates and get replaced by measured
values as gates close — the sim is a harness for reality, never a substitute for it.

## Consequences
Economics PRs carry sim output in the description. The sim grows with every new
mechanism (it is a test, not a demo). Results live in `sim/results/summary.json` and
are re-runnable by anyone — the dashboard culture of Law 8 starts in the repo.

## Exit / Reversal
Retiring the sim requires an ADR showing the mechanisms it guards are fully measured
on live flows — until then it is load-bearing.

## Evidence links
`sim/simulate_economy.py`; `sim/results/summary.json` (invariant true, Law-9 margin
positive on all seeds, treasury solvent); docs/08 §1.
