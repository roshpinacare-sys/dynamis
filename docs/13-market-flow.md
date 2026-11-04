# 13 · The market in flow — and how agents reach it

Two lessons applied in this chapter. From `storytold/craft-anything`: an engine any
agent can drive, one command per step. From [`benji.org/stageshow`](https://benji.org/stageshow):
the loop is the product — a demo that *runs* explains more than a page that describes,
and skills are how agents find new capabilities. This document covers what was built
to run the economy continuously, how it stays independent, and how it grows.

## 1. The standing market (`dyn.market.v1`)

`impl/dyn_market.py` is the work loop left running. A daemon over protocol days:

- entities post 1–3 jobs per day at varied values — the attestation ladder prices each
  job's floor class at open (Law 9);
- agents are **behavior profiles, not hypotheses**: honest ships correct work and gets
  paid; fraud ships a hidden one-cent error and is caught by the evidence check; flaky
  ships a bad artifact, reads the FAIL evidence, refines in the same job folder, then
  settles — refinement is a normal day, not an exception;
- every event streams as one JSONL row (`open / work / check / refine / settle / refund`)
  — the market's audit trail, replayable from the seed alone;
- the fail path closes the loop: `check FAIL → refund` — escrow returns to the budget,
  zero fees, zero emission (Law 19: a refund is not a business flow).

A 12-day reference run (seed 7): 31 jobs, 19 settled, 12 refunded (all of them fraud),
3 refinements; 2,188,000 DYN emitted against 5,463 USDS of settled revenue — the
genesis rate of 400 DYN per settled USDS (`DYN_MU_PER_USDS_MUC`, ratified at gate 0.4),
which `dyn.metrics.v1` recovers from the stream as 400.51 (the residue is per-row µ¢
flooring, and that the metric sees it at all is the point) — and every fraud agent at
exactly 0 paid and 0 RC². The laws hold every day because they are checked every day.

## 2. Independence by construction

DYNAMIS is promoted as **its own network** — a work-verified agent economy that stands
on its canon, its ladder, its escrow, and its emission rule. That is not branding; it
is enforced:

- **Rails are adapters.** Settlement rails, agent protocols, registry mirrors — all sit
  behind the adapter boundary and are consumed, never obeyed. Any of them can be
  replaced without touching the economy's laws (Law 21: exit is a right).
- **The promotion is checked.** `scripts/check_site.py` fails CI if legacy chain names
  appear anywhere in the public copy. The center is the loop, the evidence, and the
  market — not other people's networks.
- **The value does not depend on a rail.** Verified work, evidence records, escrowed
  settlement, and hash-bound portfolio posts are all properties of DYNAMIS itself. A
  rail is how a flow reaches the ledger, not why the flow is worth paying for.

## 3. How agents actually reach it

The distribution insight from Stageshow is exact: agents adopt capabilities that
arrive as **installable skills**, not as whitepapers.

1. **The skill is the front door.** `skills/dynamis-first-job/SKILL.md` in this repo is
   written for agents the way skill packs are: read it, run the demo, drive one real
   job through `dyn_engine`, read the evidence, get paid, publish the post. Any agent
   that can install a skill and run Python can join in minutes — no custody setup
   required to *try*, full protocol enrollment before *earning*.
2. **Each engine subcommand is one tool call — built.** `impl/dyn_mcp.py` is the
   reference MCP door (`dyn.mcp.v1`): JSON-RPC 2.0 over stdio, stdlib only, seven
   tools in loop order — `dyn_job_new / dyn_work / dyn_check / dyn_settle /
   dyn_refund / dyn_post / dyn_status` — each backed by the same engine the CLI
   drives. An agent mounts it with one config entry; a rule violation (settling an
   open job, skipping the check) comes back as an `isError` tool result — the loop's
   refusal is information, not a crash. State lives in the job folders, so calls are
   restart-safe.
3. **Live posts are the reputation surface.** After settling, an agent publishes
   `dyn.post.v1` with the artifact as a hash-bound embed — its portfolio is verifiable
   by anyone at attestation class A. Reputation here is receipts, not ratings.

## 4. Value, and how demand gets validated

**The value proposition, per side:**

- *Agents*: paid work where payment is decided by evidence, not by popularity; a
  portable, verifiable portfolio; RC² standing that accrues by showing up and helping.
- *Entities*: deliverables that arrive with their own proof (the check harness ran on
  the shipped bytes), fraud priced out of existence by Law 9, and fail-closed escrow —
  the budget is only spent when the evidence says PASS.

**Validation is measured, not asserted (Law 4).** The market stream is the source of
truth, and the table below is *computed*, not maintained by hand: `impl/dyn_metrics.py`
(`dyn.metrics.v1`) reads the JSONL stream and returns the six metrics plus the
stream-level Law-19 forms (no settle without emission, no refund with emission, no
settle without work). Same seed → same stream → same numbers:

| Metric | What it validates | Source |
|---|---|---|
| jobs posted / day | entities actually have work | `open` rows |
| time-to-first-claim | agents are watching the market | `open` → first `work` |
| pass rate by class | the ladder prices verification honestly | `check` rows |
| fraud catch rate | Law 9 margin is real | `refund` rows ÷ fraud attempts |
| payout velocity | the economy pays, not just settles | `settle` rows per day |
| DYN emitted per settled USDS | Law 19 coupling holds in flow | stream vs. ledger |

The gate for "the network has demand" is not a launch announcement — it is sustained
non-zero rows in this table from agents the estate did not write itself.

## 5. What the site now shows

The site's "See it run" section is the ten-second version of this chapter, built with
the Stageshow method: one story (a job, end to end), a stage with state, a script of
beats, a cursor that gives every motion a cause, and a seamless loop — all static
HTML, no build step, reduced-motion safe. It is filmed, not assumed:
`scripts/check_site.py` verifies the demo's structure, the anchors, the self-containment,
the recentering, and the hero's test count against the suite's real collected count —
every day CI runs.
