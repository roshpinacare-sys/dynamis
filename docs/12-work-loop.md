# 12 · The work loop — an engine, not a landing page

Pattern credit where it is due: [`storytold/craft-anything`](https://github.com/storytold/craft-anything)
showed what agent-native tooling looks like — a **loop** (study → build → check →
refine), a **project folder** as the unit of work (`craft.json`, `capture/`, `app/`,
`checks/`), **evidence records** with confidence, coverage and limitations, and an
agent-first CLI where every step is one command. This document is DYNAMIS running that
same shape where it pays. The lesson applied: a protocol that agents cannot *drive* is
a landing page; a loop they can drive is an economy.

## 1. The loop, mapped

| craft-anything | DYNAMIS (`impl/dyn_engine.py`, `dyn.engine.v1`) | What makes it economic |
|---|---|---|
| study the target | `job_new` — the job spec + deterministic input generated once, hashed into the worklog | the target is a **schema-validated object with escrow behind it** (Law 9 floor class priced at open) |
| build (coding agent) | `work` — drop any artifact into `artifact/`; the engine is builder-agnostic | the artifact's sha256 enters the claim |
| check against the original | `check` — the evidence harness: 4 checks, machine-readable records | checks are **class A/B on the attestation ladder**, not vibes |
| refine | re-`work` + re-`check` in the same folder | the evidence index resets per run — only the latest run vouches |
| — (nothing at stake) | `settle` — escrow split, flow-gated emission (Law 19) | **fail-closed: no PASS evidence, no payout path** |
| share the result | `post` — `dyn.post.v1` with the artifact as a hash-bound embed (docs/11) | the portfolio entry is verifiable |

## 2. The project folder

```
jobs/invoice-batch-500/
  dyn-job.json     worklog: job wire object, target contract, status, history, evidence index
  inputs/batch.json  the target — 500 deterministic invoices; sha256 pinned in the spec
  artifact/          the work (built by any coding agent)
  evidence/          check records: verdict, class, confidence, coverage, limitations, measurements
  post/              the published dyn.post.v1 wire object + rendered preview
```

The worklog is the agent-side record. The hash-chained escrow events inside
`dynamis_core` remain the protocol record of the money; the engine composes on
`AgentKit.open_job / claim / witness_verdict / settle` — it duplicates nothing.

## 3. The checks (and their honest limits)

Every evidence record carries `limitations` — an evidence record that cannot say what
it does *not* cover is propaganda, not measurement:

1. **`artifact_runs`** (class B) — the artifact executes as a process and writes its
   contract output. *Does not judge correctness.*
2. **`contract_shape`** (class A) — exact key set, integer-only values (the canonical
   rule), batch id, count. *Shape only.*
3. **`totals_match_ground_truth`** (class A) — per-currency totals against an
   **independent aggregation** of the same input (the checker is not the artifact's
   code path — the same double-implementation idea as sampled re-execution).
   *Catches aggregation bugs, not input bugs.*
4. **`bounded_runtime`** (class B) — wall clock under the spec's bound on this runner.
   *One runner; no cross-device variance sampled here.*

Overall verdict = all PASS. `settle` re-reads every evidence record from disk before
any money moves and refuses on anything that is not a PASS — tampered inputs, stale
FAIL records from an earlier refine round, or a skipped check each stop the loop with
`ENGINE REFUSED`.

## 4. Driving it

```bash
python3 impl/dyn_engine.py job_new jobs/demo --job-id job-demo-001
python3 impl/dyn_engine.py work    jobs/demo invoice_parser.py
python3 impl/dyn_engine.py check   jobs/demo
python3 impl/dyn_engine.py settle  jobs/demo
python3 impl/dyn_engine.py post    jobs/demo
python3 impl/dyn_engine.py demo     # the whole loop offline, on the bundled artifact
```

Each subcommand is one tool call — the same "any agent can drive the same engine the
app uses" property craft-anything built, here against the escrow/ladder/emission core.
MCP/ACP wrappers are the same commands behind a protocol; they land at gate 2.4
(docs/04-integration.md §3).

## 5. What this changes about the roadmap

The engine is the missing middle between the protocol core (which was tested) and the
network (which needs witnesses and custody). From here, the path to a *used* system is
narrower: real builders behind `work` (any coding agent already qualifies), real
runners behind `check` (specs/benchmarks.md §3 devices), and the chain core under the
folder format. Everything else — the landing page included — is downstream of agents
actually running this loop.
