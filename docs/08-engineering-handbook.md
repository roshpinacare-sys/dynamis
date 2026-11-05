# 08 · Engineering handbook — how the executing agent works in this repo

`AGENTS.md` is the contract (what you may not do). This file is the craft (how to do
the rest well). Both bind.

## 1. Sim-first development (ADR-0005)

Every change to emission, verification, pricing, or market mechanics lands in this
order: **simulate → reference-implement → gate**. The simulator (`sim/`) is the
falsifiable model of the economy; if your change makes Law 9 margins negative or the
treasury insolvent in any seed, the change is wrong — fix the design, not the seed.

```bash
cd impl && python -m unittest discover -s tests -v     # 61 tests — keep green
cd .. && python sim/simulate_economy.py                # invariant exact, margins ≥ 0
```

Committing protocol changes with a red suite or a broken invariant is a gate violation,
not a style issue.

## 2. The repo is the machine's memory

- Docs update in the same commit as the behavior they describe (`git = existence`).
- Numbers: `params/genesis.yaml` first, then code constants named after the param.
  Never inline a bare dollar literal — `usds(n)` exists so units cannot lie.
- New services register ports in `params/genesis.yaml#ports`; the `:3040` collision is
  the standing example of what happens when this is skipped.

## 3. Service checklist (Definition of Done for anything that runs)

- [ ] `/health` (200, unauthenticated) and `/status` (503 unless authenticated).
- [ ] Deny-by-default on every input surface (the G28 pattern).
- [ ] Integer money only; canonical JSON at the boundary (specs/wire.md §1).
- [ ] Kill switch armed and drill-tested (specs/testing.md §1).
- [ ] Structured log line per state transition; receipts before consensus (Law 4).
- [ ] Exit runbook block in the integration file (Law 21) — written the day it ships.

## 4. Working with gates

1. `specs/gates.yaml` is the only queue. Find the earliest open package.
2. Work exactly its acceptance line; do not improve the criterion while working it
   (that is an ADR, filed separately).
3. Append evidence to `specs/acceptance/EVIDENCE.md`: command, exit code/hash, date.
4. If blocked on the owner, write `outbox/BRIEFING.md` with a recommendation and move
   to the next gate-legal package — never idle, never improvise around a gate.

## 5. Code style (the fleet's conventions)

- Python: stdlib-first, type-hinted, dataclasses for protocol objects, `unittest` (no
  external test deps), fail-closed constructors.
- Money/time: integers only (`usds()`, protocol days). Floats in a canonical payload
  raise — keep it that way.
- PRs (or direct commits on packages you own): one package per commit, message cites
  the package id (`0.4: ratify genesis params`).
- Comments state constraints the code cannot show (laws, invariants, units) — never
  narrate what the next line does.

## 6. Incident behavior

- Find a broken invariant or a custody hole: stop the affected path (kill switch),
  record the finding in EVIDENCE.md and `outbox/BRIEFING.md`, then fix. Failures are
  reported as failures, with the error (AGENTS.md §7).
- A law conflict (two laws pull opposite ways): the canon wins; file the ADR proposing
  the canon amendment; the regulator decides with veto keys.

## 7. What good looks like

A gate closes and a stranger can re-derive it: run the command in the evidence line,
get the same exit code. The honest-budget dashboard shows the gap between target and
measured without embarrassment — that visibility is the product's credibility, and the
credibility is the moat.
