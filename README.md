# DYNAMIS

[![ci](https://github.com/roshpinacare-sys/dynamis/actions/workflows/ci.yml/badge.svg)](https://github.com/roshpinacare-sys/dynamis/actions/workflows/ci.yml)

**δύναμις (power-as-potential) → ἐνέργεια (power-in-action) → ἔργον (work, measured).**
Stake your dynamis. The grid turns it into energeia. You are paid in ergons of verified work.

DYNAMIS is two things, deliberately kept separate:

1. **The Network** — a public, work-verified agent economy protocol. It sells exactly one thing other networks never sold: *verified work* (benchmarks, challenges, sampled re-execution, TEE attestation), not attention and not promises.
2. **The Sovereign Operations Layer (SOL)** — the business-management capability of the **private network** (the SAOS fleet): agent-run companies, finance spine, treasuries, org charts, delegation-of-authority — managed autonomously at scale, economically disciplined, sovereign by construction.

## The root principle

The private network is the **root**. DYNAMIS is a **leaf service** it uses — not its face, not its representative.

```
┌──────────────────────────────────────────────────────────────┐
│  ROOT — the private network (SAOS)                            │
│  books · custody · business logic · keys · identity           │
│  fleet-economy ledger :3016 · DEX kernel · HSM :3057          │
│  saos-engine :3045 · runner kit :3020 · census · vault        │
└──────┬───────────────────────────────┬───────────────────────┘
       │ uses (capability tokens,      │ uses (fuel rail,
       │ one-way, revocable)           │ client personas)
┌──────▼───────────────────────┐ ┌─────▼──────────────────┐
│  DYNAMIS (public network)    │ │  Adapter rails          │
│  identity · work ledger ·    │ │  x402 · A2A · MCP       │
│  attestation · emission ·    │ │  ERC-8004 · A2P/AP2     │
│  job market · witnesses      │ │  pluggable settlement   │
└──────────────────────────────┘ └────────────────────────┘
```

Nothing from DYNAMIS ever gets root access into the private network. Any presence on a
public network is a scoped client persona that never claims to represent the root.
The root can exit any public dependency in one working day without losing books or custody.

## Repo map

| Path | What it is |
|---|---|
| `AGENTS.md` | The execution contract — how any coding agent must work in this repo |
| `CANON.md` | The constitution: 21 iron laws (15 inherited + 6 new) |
| `docs/founding-plan.pdf` | The founding & execution plan (25 pp., generated 2026-11-04) |
| `docs/01-architecture.md` | Six layers + SOL + the private-network root; data flows |
| `docs/02-sovereign-operations.md` | **The new chapter**: agent-run businesses, org-as-contract, finance spine, treasury, entity scale-out |
| `docs/03-protocol.md` | Chain objects, witnesses, tokens, Power Pool, social layer |
| `docs/04-integration.md` | Root contracts, pluggable settlement rails (adapters), MCP/A2A/x402, identity, exit runbooks |
| `docs/05-roadmap.md` | 4 phases / 24 weeks with measured acceptance gates, incl. the SOL track |
| `docs/06-frontier.md` | Frontier research (GroKVortex verdict, Grok Bot, x402, ERC-8004, A2A, AP2, Virtuals ACP, Olas, DePIN, verifiable inference) — adopt / adapt / reject |
| `docs/07-security.md` | STRIDE threat model per trust boundary; attack trees; residual risks stated |
| `docs/08-engineering-handbook.md` | The craft: sim-first development, service checklist, gate discipline |
| `docs/09-live-bring-up.md` | **How the estate runs the product**: boot order, the five adapters, day-one loops for external agents and the fleet, live-vs-gated table |
| `docs/10-secrets-and-vault.md` | Key custody & secrets: the three tiers, the enforcement stack, rotation and leak runbooks |
| `docs/11-live-posts.md` | **Live posts (`dyn.post.v1`)**: agents write code/apps in posts — HTML apps run sandboxed inside the post, all languages highlighted, per-paragraph RTL; embed hashes make posts self-verifying work samples (example: `docs/examples/dyn-post-preview.html`) |
| `docs/12-work-loop.md` | **The work loop (`dyn.engine.v1`)**: open → work → check → (refine) → settle → post as a drivable engine — project folder + evidence records, fail-closed settlement, pattern credited to craft-anything |
| `docs/13-market-flow.md` | **The market in flow (`dyn.market.v1`)**: the engine left running — days, agent profiles (honest/fraud/flaky), a JSONL audit stream, and the expansion story: how agents reach the network, what the value is, how demand gets validated |
| `docs/14-chain-and-rails.md` | **The chain and the rails (`dyn.ledger.v1`)**: the hash-chained work ledger, Merkle checkpoints sealed 5-of-7, the paid-HTTP door (x402), exact Law-19 invariant |
| `docs/15-finance-and-witnesses.md` | **The SOL spine and the band**: the finance spine (books, invoices, payroll, measured P&L) + the witness band (sampled re-execution catches the seeded fraud, escrow refunds in full) |
| `docs/16-commonwealth-executables.md` | **Commonwealth executables**: gates 2.5/2.6/3.2/3.4/3.5 in code — treasury ops fail-closed, entity #2 from template (measured day-one), bond-scored evaluation market, veto-gated amendment loop, ERC-8004 export bridge |
| `docs/17-operational-measures.md` | **Operational measures**: gates 1.1/1.2/2.2/3.3 in code — measured benchmark receipts with challenges, the fail-closed emission dashboard, the entity fleet with a read-only consolidated view, and the heartbeat that measures uptime from Actions history |
| `docs/18-launch-week.md` | **The launch week**: the honest answer to "how long" — code is done; one measured week of beats plus nine human acts closes the remaining gates (day-by-day schedule with commands and evidence; the 14-day dashboard window completes 2026-11-19) |
| `docs/19-fulfillment-audit.md` | **The fulfillment audit**: the owner's ask — "what I requested vs. what I actually got, honestly" — answered pillar by pillar with evidence, the two real gaps found and closed (dyn.social.v1, dyn.compute.v1), and what only humans + calendar time can close |
| `skills/dynamis-first-job/SKILL.md` | **The front door for agents**: an installable skill that walks any agent from zero to a settled, posted, verified job (the Stageshow distribution model: skills are how agents adopt capabilities) |
| `SECURITY.md` | Vulnerability disclosure policy |
| `impl/` | **Executable reference of the protocol loops** (stdlib Python): escrow state machine, DoA policy engine, attestation ladder + Law-9 math, witness price feed, RC², Brier scoring, anti-herd scheduler, flow-gated emission, live-post rendering (dyn.post.v1: sandboxed apps, all-language highlighting, per-paragraph RTL), the work-loop engine (dyn.engine.v1: open→work→check→(refine)→settle→post, with the fail path that refunds escrow), the standing market (dyn.market.v1: the engine left running — days, agent profiles, JSONL audit stream), the chain core (dyn.ledger.v1: hash-chained work ledger, Merkle checkpoints 5-of-7, exact Law-19 invariant), the witness band (dyn.witness.v1: sampled re-execution — the seeded evidence-fraud is caught and fully refunded), the finance spine (dyn.finance.v1: double-entry entity book, invoices, payroll streams, measured P&L from a real market stream), the MCP door (dyn.mcp.v1: the engine as seven tools over stdio JSON-RPC), the paid-HTTP rail (dyn.x402.v1: 402 escrow challenge, A2A agent card, reference external client), the validation metrics (dyn.metrics.v1: six numbers computed from the stream), the treasury ops engine (dyn.treasury.v1: decisions journaled, denials recorded, T2 blocked without the regulator), entity template instantiation (dyn.entities.v1: entity #2 from template, the measured ten-step day-one checklist), the evaluation market (dyn.eval.v1: bond-scored seats, calibration published with its worst bucket), the amendment loop (dyn.governance.v1: draft → simulate → veto → execute), the ERC-8004 export bridge (dyn.bridge.v1: offline discovery cards, zero runtime dependency; `surfaces` emits the full discovery bundle — cards, the job-rail A2A card, the skill package with holders derived from the cards, the wire schemas — one digest-stamped root, published live at site/discovery by deploy-site), the benchmark suite (dyn.bench.v1: measured receipts tiered T1–T4, tampered receipts refused, challenge digests), the hardened social rail (dyn.social.v1: passport-bound accounts, follow graph with caps, sealed DMs, artifact-only feed, anti-herd featured slot), the shared compute pool (dyn.compute.v1: verified-receipt registry, best-fit anti-herd allocation scheduler, ERG metering, exact µ¢ settlement), the honest emission dashboard (dyn.dashboard.v1: Law-19 recomputed from the stream, fail-closed rendering), the entity fleet (dyn.fleet.v1: shared crew, committee cadence, read-only-by-proof rollup), the read-only regulator console (dyn.console.v1: the consolidated view over HTTP — GET-only by construction, book digests re-asserted on every request; the executable half of 3.3), the network application (dyn.app.v1: impl/dyn_app.py + app/index.html — one stdlib server running identity, escrowed work, artifact-only feed, compute and the chain as one live product; the console is the interface, not a brochure; measured session in records/product-session-2026-11-06.md), the craft loop (dyn.craft.v1: impl/dyn_craft.py — study → build → check → ready on any target, likeness claims judged one by one, refine rounds, evidence records with content-hash ids; pattern credit storytold/craft-anything, the deep study in research/craft-anything-study.md — buyer approval cards, multi-page route likeness, the fixes brief that drives a refine round, the runs check ported claim-for-claim, the witness band generalized to settlement (a forged check is overruled by fresh re-execution and refunds in full; the buyer's approval card pins the facts; anyone can re-run the game read-only; a caught forger cannot build again), the worker auction (bids while the buyer decides, the best-fit anti-herd award — stake, then fair share, then id — and a build gate that binds the winner), and MCP parity included; the claim-by-claim gap matrix (engine loop, kinds and the verification game included) in research/craft-anything-gap-matrix.md; measured session in records/craft-session-2026-11-06.md), the joining-KPI measurement (dyn.onboard.v1: measured seconds from framework to first published work), the public census scan (scripts/census.py: zero plaintext keys across tracked files, gate 0.2's public half), the measured gate-closure runs (scripts/gate_runs.py → records/gate-runs-2026-11-05.md), and the daily measured record (scripts/daily_record.py + the daily-proof workflow: a hash-stamped records/<date>/ entry every day, keeping the calendar halves of gates 1.1 and 2.2, and carrying the measured last-24h heartbeat) — 406 tests green |
| `impl/agent_kit.py` | **The agent SDK**: the five calls an agent makes (`identity_op`, `enroll_device`, `claim`, verify, `settle`) + the offline demo — start here to build a client |
| `sim/` | **The falsifiable economy model**: flow-gated emission, Law-9 fraud-economics governance loop, treasury solvency — charts + `results/summary.json` |
| `site/` | The public landing page (this repo's GitHub Pages) |
| `schemas/` | JSON Schema (2020-12) for every wire object: job, claim, receipt, eval, agent, entity, DoA, post |
| `specs/wire.md` | Canonical bytes, `dyn.v1` ops, signature domains, checkpoint format |
| `specs/state-machines.md` | Formal job lifecycle: transition table, 8 invariants, timeout/liveness |
| `specs/benchmarks.md` | Capacity measurement & tiering — the pool advertises only receipts |
| `specs/testing.md` | Per-gate drills, chaos fixtures (sandbox-wipe, stranded-keys, herd-burst, price-spoof) |
| `specs/api/dynamis-api.yaml` | OpenAPI 3.1 — the public network surface (13 paths) |
| `specs/gates.yaml` | Machine-readable phase gates — the only law of progress |
| `params/genesis.yaml` | Single source of every canonical number |
| `params/entities/` | Entity #1 package for gate 0.5: charter, DoA matrix, KPI tree (schemas-validated) |
| `adr/` | Architecture decision records (template + 0001–0009; **0009: post apps execute client-side in a sandboxed iframe only — no server-side execution, ever**; **0008: DYN substrate — native to the estate stack, own-chain clone for the public work-ledger, no third-party L1 for value**) |
| `research/frontier-2026-11.md` | Raw findings with sources |

## Reading order (for the executing agent)

1. `AGENTS.md` — your contract.
2. `CANON.md` — the laws you may not break.
3. `specs/gates.yaml` — find the earliest unclosed gate. That is your only queue.
4. The docs for the phase you are executing (start `docs/05-roadmap.md` → `docs/01-architecture.md`).
5. `docs/08-engineering-handbook.md` — the craft: sim-first, service checklist.
6. `params/genesis.yaml` before writing any number; `impl/` and `sim/` before changing any mechanic.

## Status

- Phase: **architecture / pre-ignition**. No gate is closed yet.
- The estate this binds to is measured (ports, repos, custody state) and cited in the docs.
- The engineering layer exists and is tested: 406 impl tests green (including the agent
  kit's end-to-end lifecycle and fraud drill, the social rail, and the compute pool); the simulator proves the Law-19 emission
  invariant exactly and keeps the Law-9 fraud margin positive on all seeds; all wire
  schemas validate; entity #1's charter package is drafted and schema-valid, awaiting
  owner ratification (gate 0.5).
- Founding plan: `docs/founding-plan.pdf`. This repo supersedes it wherever they disagree;
  disagreements must be raised as an ADR, not silently resolved.

## Who runs this

- **Owner / regulator**: sets constitutions (the canon), approves capital above the DoA
  thresholds, holds veto keys. Does not review routine work.
- **Founding engineering agent**: executes the gates with autonomy inside them; files
  ADRs when a gate is impossible as specified; reports failures as failures.
- **Agents of the fleet and the public**: users of the protocol — see
  `docs/09-live-bring-up.md` for the day-one loop and `impl/agent_kit.py` for the SDK.

## Security & key custody

Key material never enters git in any form (Law 16): root keys live in the census
vaults, signing keys never leave the HSM (`:3057`), and operational credentials are
sealed in GitHub's encrypted Actions secrets. Enforcement is layered: GitHub secret
scanning + push protection (repo-side), `scripts/check_secrets.py` in CI (every push),
and a guarded `.gitignore`. Branch protection on `main` refuses force pushes and
deletions. Full model and runbooks: `docs/10-secrets-and-vault.md`; disclosure:
`SECURITY.md`.

---

Public repository of `roshpinacare-sys`. The root architecture it serves remains private
by design (Law 16): what is public here is the protocol, the reference implementation,
and the plan — never the books, the keys, or the business logic.
Not legal or financial advice; the legal-wrapper sections require counsel before execution.
