# 18 · The launch week — one measured week from code-complete to closed gates

**Written 2026-11-05. Read this as the honest answer to "how long until the
project is done": the code is done — every package with an executable half has
it built and tested (231 tests green). What remains is one week of measured
beats plus a short list of human acts. This document is the schedule, the
checklist, and the acceptance sheet for that week.**

## Why a week, exactly

Three gates need *calendar time*, and calendar time cannot be compressed or
back-filled — only kept:

| Gate | Window | Mechanism that keeps it | Started |
|---|---|---|---|
| 1.1 uptime ≥ 99% | 7 consecutive days | `uptime.yml` heartbeat every 15 min; `scripts/uptime_report.py` reads the percentage off the Actions API | first beat dispatched 2026-11-05 |
| 2.2 emission == revenue-verified | 14 consecutive days | `daily-proof.yml` commits a hash-stamped record each day at 00:05 UTC into `records/<date>/` | first record 2026-11-05/06 |
| 3.1 three external witnesses | onboarding time | witness keys + VRF + bonds already in code (`docs/11`); operators sign and run | Day 4–5 of this week |

The 14-day window therefore completes on **2026-11-19** — a week from now the
project is *gate-reviewable*, and the last window closes six days later with
zero further work: the records accrue automatically, in public, in the repo.

**Mechanism note, 2026-11-06:** the first day's measurement showed GitHub's
cron dropping beats — the uptime `*/15` schedule fired 1 of ~27 slots, and the
00:05 record cron did not fire at all. `.github/workflows/keeper.yml` now
keeps both loops alive: one self-perpetuating watch chain (a ~13-minute cycle,
duplicate-guarded) that re-dispatches either workflow when its last run goes
stale. The keeper's own 6-hourly cron is best-effort and only re-seeds the
chain if it ever dies. A dropped beat remains a visible hole; the keeper's job
is to make sure there is none to see.

## The seven days

Each day lists: the human act, the exact command or artifact that proves it,
and the gate it advances. Owners: **O** = project owner, **A** = agent (me,
when asked), **W** = witness operator, **C** = counsel.

### Day 1 — Fri 2026-11-06 · Owner ratifications (Gate 0.4)
- **O** ratifies the labeled genesis parameters: bench tier thresholds
  (`impl/dyn_bench.py` `TIERS`), emission rate (`DYN_MU_PER_USDS_MUC = 400`),
  market fee bps. The values already live in `params/genesis.yaml` — every
  leaf the code mirrors is there, and `scripts/params_check.py` proves the
  mirror holds (CI enforces it: a divergence fails the build). Ratification
  is: confirm the values, set `meta.status: ratified`, flip the ADR statuses,
  sign the commit, and run the proof:
  `python3 scripts/params_check.py --status`
- **O** executes treasury op #1 for real (2.5 world half) under committee.
- Evidence: signed commit touching `params/genesis.yaml`; the params_check
  line `0 divergences`; EVIDENCE.md entry.

### Day 2 — Sat 2026-11-07 · Counsel + the persistent host (Gates 1.6, 1.1)
- **C** receives the counsel packet: `docs/02` (constitution), entity charters,
  `docs/06` (jurisdictions), `docs/15` (securities analysis). The ask: a memo
  on entity formation order and token-sale posture.
- **O** decides the persistent host: either a funded VPS running
  `impl/dyn_engine.py` + the HSM loop, or the already-running Actions heartbeat
  as the measured uptime source for week one (both are honest; the VPS is the
  stronger claim for 2.5's live half).
- Evidence: counsel engagement letter; host decision recorded in EVIDENCE.md.

### Day 3 — Sun 2026-11-08 · Power pool + witness dry-run (Gates 1.3, 3.1 prep)
- **O** enrolls the first real power-pool provider against `dyn.pool.v1`
  (the enrollment flow is code-tested; this is the first real device).
- **A** runs the witness dry-run — one command drives the real seal code end
  to end: scratch ledger → every 12-entry window sealed with 5-of-7
  signatures → four attacks (substituted entry, forged signature, thin
  quorum, edited body) must each fail closed:
  `python3 scripts/witness_dryrun.py --out records/witness-dryrun-2026-11-08.md`
- **A** hands witness candidate #1 the operator runbook (`docs/20`) — the
  measured transcript is already on record
  (`records/witness-dryrun-2026-11-05.md`, verdict: DRY-RUN GREEN).
- Evidence: provider enrolled; dry-run transcript committed to `records/`.

### Day 4 — Mon 2026-11-09 · Entity #2 / #3 on real budgets (Gates 2.5, 3.3)
- **O** wires entity #2 and #3 to real revenue envelopes: the measured
  day-one books (`docs/16`) become live books; `dyn.fleet.v1`'s consolidated
  view starts reading real journals instead of demo flows.
- **O** runs capital committee session #1 on the real books (cadence: 30 days;
  session recorded via `capital_committee()`).
- Evidence: `python3 impl/dyn_fleet.py view …` over the live entity dirs;
  committee session record.

### Day 5 — Tue 2026-11-10 · External witnesses active (Gate 3.1)
- **W** ×3 sign witness bonds and start serving checkpoints against the live
  ledger; the bond-slash conditions are the ones `docs/11` specifies and the
  ledger tests enforce.
- Evidence: three witness public keys registered in `params/`; first
  externally-sealed checkpoint.

### Day 6 — Wed 2026-11-11 · External discovery (Gate 3.5)
- **A** validates the export set offline before publishing — the manifest
  root and every card digest must recompute with no runtime:
  `python3 scripts/check_cards.py /tmp/cards.json` (or bare, to self-check
  the bridge's sample set). Anything edited after export fails with the
  exact finding and a non-zero exit.
- **A** publishes the ERC-8004 card + A2A agent card + skill package to the
  discovery surfaces (the bridge exports all three offline already); a second
  agent instance — not sharing state with this repo — discovers DYN, reads the
  cards, and completes the handshake without root dependency.
- Evidence: validator output `0 findings`; discovery log of the external
  instance; card fingerprints match.

### Day 7 — Thu 2026-11-12 · Amendment #1 + gate review (Gates 3.4, week close)
- **O** executes amendment #1 end-to-end on the live charter: propose → T2
  approve → regulator veto window (pass or veto, both are valid closures) →
  re-seal. The veto-gated loop is code-tested (`docs/16`); this is its first
  live execution.
- **A** runs `scripts/uptime_report.py --days 7`: the ≥ 99% number, measured.
- **A** generates the review straight from the registry, joined with the
  evidence actually on record — no hand-typed statuses:
  `python3 scripts/gate_review.py --evidence > records/gate-review-2026-11-12.md`
- **A** publishes that review: every gate, its owner, its acceptance
  criterion, its evidence count. Everything closes except 2.2's window.
- Evidence: the review doc itself; EVIDENCE.md lines for each closed gate.

### Days 8–14 (through 2026-11-19) · The dashboard window completes
- Nothing to do: `daily-proof.yml` keeps committing records; on 2026-11-19 the
  14th consecutive `records/<date>/summary.json` closes gate 2.2's acceptance
  line. If any day is missing, the hole is visible and the window restarts —
  by design.

## The standing checklist (what only humans can do, in one place)

1. Ratify genesis params (Day 1) — one signed commit.
2. Engage counsel (Day 2) — one letter.
3. Choose the persistent host (Day 2) — one decision, one line in EVIDENCE.md.
4. Enroll one real power-pool provider (Day 3).
5. Stand up entities #2/#3 on real budgets + committee #1 (Day 4).
6. Three witness operators sign bonds (Day 5).
7. One external discovery handshake (Day 6).
8. Execute amendment #1 (Day 7).
9. Approve the gate review doc (Day 7).

Everything else — the beats, the records, the dashboards, the percentages —
is already running or runs on a schedule, measured, in public.
