# 05 · Roadmap — four phases, measured gates, the SOL track

Executed per `specs/gates.yaml` (machine-readable). Owners: **O** = owner/regulator
decisions, **A** = executing agent. A phase starts only when the earlier gate is closed
with evidence (the fleet's own anti-fantasy rule).

## Phase 0 — Ignition (weeks 1–2)

Custody, canon, and the first entity. Everything else waits.

| # | Package | Owner | Acceptance gate |
|---|---|---|---|
| 0.1 | Name clearance: trademark + domain check for DYNAMIS (frontier found name-adjacent scams: see `docs/06` §1) | O | cleared name or alternate chosen; recorded |
| 0.2 | Custody first: two-soul vault for all new keys **before** any code touches them; census lists zero plaintext keys on disk | O + A | census run passes; 0 findings |
| 0.3 | Re-key or formally retire the dead army: 46 ROT2 WIFs, LOST-WITH-SANDBOX accounts; owner decision on `Saosmartwallet/db/custom.db` (248 entries) | O (decide) / A (draft) | decision recorded in `CUSTODY.md`; census updated |
| 0.4 | Genesis parameters: ratify `params/genesis.yaml` (this repo's canon commit) | O | params committed; ADR-0001..0004 merged |
| 0.5 | **Entity #1 charter**: the network's own operating entity — charter, DoA matrix, budgets, KPI tree, regulator named (Law 20) | O | entity object live in `params/entities/` |
| 0.6 | Port hygiene: resolve the `:3040` collision (saos-engine vs office-selfcheck) | A | both services healthy on distinct ports |

**Gate 0**: census clean + entity #1 charter live + params ratified.

## Phase 1 — Spark (weeks 3–6)

First real power and the finance spine.

| # | Package | Owner | Acceptance gate |
|---|---|---|---|
| 1.1 | Persistent host for 24/7 services (device or funded Actions) — the audit found nothing is deployed outside the owner device | O (budget) / A (build) | engine + HSM + economy uptime ≥ 99% measured over 7 days |
| 1.2 | Benchmark suite (L1) + challenge client (L2) on the runner kit | A | 3–5 devices enrolled, tiered from measured throughput |
| 1.3 | **Finance spine v1** (SOL): chart of accounts + entity #1 book + invoice issuance + chain anchoring of digests | A | first real invoice issued and settled end-to-end; digest anchored ~$0.10 |
| 1.4 | Worker registry + payroll streams (SOL): agent → role → rate → USDS stream | A | first agent salary paid as a stream, booked in entity book |
| 1.5 | Job market alpha (escrowed, USDS): internal demand only | A | first paid jobs between entity #1 budget and fleet workers settle |
| 1.6 | Legal: engage counsel re: entity wrapper + management delegation | O | counsel engaged; memo filed |

**Gate 1**: ≥ 99% uptime week + first invoice-to-settlement flow measured + payroll live.

## Phase 2 — Grid (weeks 7–16)

The public network opens. External demand. Verification earns.

| # | Package | Owner | Acceptance gate |
|---|---|---|---|
| 2.1 | DYNAMIS chain: identity, work ledger, checkpoints (DEX pulse pattern), witness band v1 (7+14, VRF over custody score) | A | 3 external honest devices verify; 1 collusion caught |
| 2.2 | Emission live, **flow-gated** (Law 19): work rewards only against settled entity/external jobs | A | dashboard: emitted = revenue-verified |
| 2.3 | Power Pool: channels + attestation ladder (A–E) enforced in pricing | A | class-C sampled re-execution catches a seeded fraud |
| 2.4 | External rails: x402 endpoint, A2A cards, MCP `saos_jobs_*` | A | external machine client completes first paid job via x402 |
| 2.5 | **Entity #2** instantiation from template (SOL) | O (charter) / A | day-one checklist measured < 1 day; separate book/keys live |
| 2.6 | Treasury policy engine in kernel (DoA classes enforced, fail-closed) | A | T2 spend blocked without regulator approval — measured |

**Gate 2**: external paid work settling + fraud caught by verification + two entities live.

## Phase 3 — Commonwealth (weeks 17–24)

Open network, governed.

| # | Package | Owner | Acceptance gate |
|---|---|---|---|
| 3.1 | Witness set decentralization: external witness operators admitted under VRF + bonds | A | ≥ 3 external witnesses active |
| 3.2 | Evaluation market with bond-scored evaluators (Brier) live | A | calibration report published, no embarrassment clause honored |
| 3.3 | **Entity fleet** (SOL): ≥ 3 entities sharing crew pool + capital committee cadence | O (T2 approves) / A | consolidated (read-only) regulator view live in `giant@:3000` |
| 3.4 | Governance: charter amendments via regulator veto + ADR process | O | first amendment executed end-to-end |
| 3.5 | ERC-8004 bridge + external discovery | A | agents discoverable externally without root dependency |

**Gate 3**: three entities with measured P&Ls + decentralized witnesses + governance loop closed.

## Standing rules

- Every phase includes custody-patrol and census freshness (the 15-min/50-min beats keep running).
- The honest-budget dashboard (target vs measured, gaps unhidden) exists from Phase 1 — not at the end.
- SOL packages are first-class: a phase gate cannot close with emission live while the finance
  spine of Law 19's flow is missing.
