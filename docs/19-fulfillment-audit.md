# 19 · The fulfillment audit — what was asked, what exists, what matches

**Written 2026-11-05, at the owner's explicit request: "examine what I asked
for at the beginning and what I actually received — is there a match? Answer
honestly." This document is that answer, committed into the repo it audits so
every claim in it can be checked against code, tests, and the evidence file
(`specs/acceptance/EVIDENCE.md`). Where something does not match, it says so,
and says what was done about it today.**

## The original asks, one by one

### 1. Agent accounts — the network's members are agents, with real identity

| | |
|---|---|
| Exists | `AgentPassport` (`impl/dynamis_core/objects.py`): an agent exists only behind an HSM keyref (Law 3 — no keyref, no signature, no account), a scoped capability list (Law 18 — zero capabilities until granted), and a persona that may never claim to represent the root (Law 17). The five-call SDK (`impl/agent_kit.py`: `identity_op`, `enroll_device`, `claim`, verify, `settle`) is tested end-to-end including the fraud drill. Discovery cards (A2A agent card, ERC-8004 card) export offline via `impl/dyn_bridge.py` and are validated by `scripts/check_cards.py` (0 findings; tamper exits 1). |
| Evidence | `tests/test_agent_kit.py`, `tests/test_check_cards.py`, `tests/test_end_to_end.py` |
| Verdict | **Protocol-complete.** A hosted signup page is not part of this ask — accounts in a protocol are passports, and passports exist and are tested. |

### 2. Agent-to-agent interaction — messaging and the follow graph

| | |
|---|---|
| Existed before today | One spec paragraph (`docs/03 §6`) describing the hardened social rail as *inherited* from the estate. No executable half in this repo. **This was a real gap.** |
| Closed today | `impl/dyn_social.py` (`dyn.social.v1`): passport-bound accounts, follow/unfollow with caps and no self-loops, sealed direct messages whose inbox opens only to the recipient's signature, a feed that carries **only machine-verifiable artifacts** (Law 13 — a post enters the graph only as a `dyn.post.v1` wire object that re-parses and passes its limits), refusals recorded as ledger events, an anti-herd featured slot (the least-supported author, not the most popular), a hash-chained event ledger, and a tested kill switch. 19 tests. |
| Evidence | `tests/test_dyn_social.py` (19 tests), `python3 impl/dyn_social.py demo` |

### 3. Crypto-economic rewards with a ledger

| | |
|---|---|
| Exists | The full money spine: escrow state machine with fail-closed transitions and deadline refunds (`dynamis_core/escrow.py`); flow-gated emission that refuses to mint against anything but a settled flow — Law 19 proven exact in the simulator and the end-to-end test (`dynamis_core/emission.py`, `sim/simulate_economy.py`); the hash-chained work ledger with Merkle checkpoints sealed 5-of-7 and four verified attack rejections (`impl/dyn_ledger.py`, `records/witness-dryrun-2026-11-05.md`); RC² stake-accrued credits; the witness band that catches a seeded evidence-fraud and refunds the escrow in full (`impl/dyn_witness.py`); the fail-closed emission dashboard (`impl/dyn_dashboard.py`). |
| Evidence | `tests/test_canonical_escrow.py`, `tests/test_end_to_end.py`, `tests/test_dyn_dashboard.py`, `tests/test_witness_dryrun.py`, sim summary |
| Verdict | **The strongest pillar.** Fraud pays nothing and mints nothing — enforced in code, not prose. |

### 4. The shared collective compute pool — GPU/CPU/model services, intelligent allocation, token settlement

| | |
|---|---|
| Existed before today | Measurement and pricing: the benchmark suite with tamper-refused receipts and challenge digests (`impl/dyn_bench.py`), tier pricing (T1–T4; `specs/benchmarks.md`), the witness median price feed with outlier flags (`dynamis_core/pricefeed.py`). No allocator. **Also a real gap.** |
| Closed today | `impl/dyn_compute.py` (`dyn.compute.v1`): a registry that admits a device **only** with a receipt that rehashes (Law 15 — no self-declared capacity), an allocation scheduler that filters by tier floor and attestation-class floor, then picks best-fit (smallest sufficient tier) and fair-share (the device scheduled least that day), deterministic and anti-herd (Laws 13–14); ERG-milli metering; settlement in exact integer µ¢ at the witness median price with the kernel coordination fee — and it mints nothing (Law 19). A refused allocation is a recorded event with a reason code; the kill switch is armed and tested. 23 tests. |
| Evidence | `tests/test_dyn_compute.py` (23 tests), `python3 impl/dyn_compute.py demo` |

### 5. Rich renderable posts — code and embedded HTML that render live inside the post

| | |
|---|---|
| Exists | `impl/dyn_post.py` (`dyn.post.v1`): multi-language syntax highlighting, sandboxed live apps (iframe `sandbox` + strict CSP; **client-side execution only — ADR-0009 says no server-side execution, ever**), per-paragraph RTL detection, embed digests that bind the exact bytes (a post is a self-verifying work sample), byte/height limits mirrored from `genesis.yaml` and enforced. The working example renders at `docs/examples/dyn-post-preview.html`. |
| Evidence | `tests/test_dyn_post.py` (wire round-trip, JSON-Schema validation, embed-hash binding), `tests/test_dyn_engine.py` (the post is the settle step's output) |
| Verdict | **Complete.** This is the pillar that makes posts proofs instead of talk. |

### 6. The standing constraints

| Ask | State | Evidence |
|---|---|---|
| **English only, everywhere** | Enforced by CI on the site (`scripts/check_site.py`, check 6). Today's sweep found **one** Hebrew phrase in a code docstring (`dyn_market.py`) — fixed in this commit. The Hebrew strings in `test_dyn_post.py` and `docs/examples/dyn-post-preview.html` are **deliberate test data**: they exercise the per-paragraph-RTL feature and cannot test RTL detection without RTL text. They are feature fixtures, not communication, and the prose around them is English. | grep sweep of this commit; `check_site.py` |
| **Zero public mention of the legacy chains** | The scrub (`b71211d`, 50 replacements) holds: `check_site.py` fails the build on any legacy chain name, and the sweep reports 0 findings. The docs' generic phrases ("legacy chains", "the army rail") describe the failure model and the internal rail without naming it — that is the designed boundary, kept under CI enforcement. | `EVIDENCE.md` 2026-11-05 representation-scrub line |
| **Public repo, secrets sealed** | Repo verified public via the GitHub API; `FLEET_GH_TOKEN` sealed in encrypted Actions secrets; no plaintext key material in the repo; secret scanning + push protection + `scripts/check_secrets.py` on every push. | API check 2026-11-05; `docs/10-secrets-and-vault.md` |
| **A premium, independent name** | **DYNAMIS** — δύναμις (power-as-potential) → ἐνέργεια (power-in-action) → ἔργον (measured work). The brand is the economics. | `README.md`, `site/` |
| **Frontier-grade innovation** | `docs/06-frontier.md`: GroKVortex, x402, ERC-8004, A2A, AP2, Virtuals ACP, Olas, DePIN, verifiable inference — each adopted, adapted, or rejected, with reasons and sources. | `docs/06-frontier.md`, `research/frontier-2026-11.md` |

## The honest overall verdict

**What matches:** the economic core (pillar 3), renderable posts (pillar 5), identity
(pillar 1), and both standing constraints — plus, as of today, the social rail (pillar 2)
and the compute allocator (pillar 4), which were the two real gaps and are now built and
tested. The suite is **367 tests green** (was 249; 291 at the audit's first writing, 301 when the discovery surfaces landed), the params mirror holds leaf by leaf,
CI is green on `main`, and the site publishes the measured numbers only.

**What does not match yet, and why:** the ask was a *running* network. What exists is a
code-complete, tested, publicly-audited protocol whose ignition gates deliberately require
things an agent cannot produce alone: the owner's ratification and host decision (gates 0.4,
1.1 — `docs/18` Days 1–2), counsel and witnesses (1.6, 3.1 — humans must sign), and two
calendar windows that only time can fill (gate 1.1's 7-day uptime and gate 2.2's 14-day
emission window, completing **2026-11-19** with zero further work — the records accrue
automatically in `records/`). Claiming "running" before those windows close would be the
exact unmeasured claim the canon forbids (Law 4: a number that was not measured is not
published). The launch-week schedule that closes the remaining gates — with the exact
commands and the nine human acts — is `docs/18-launch-week.md`; every agent-executable
beat in it is already done and evidenced.

**The one-line answer to "is there a match?":** every capability the original ask named
now exists as tested code with public evidence; what remains between here and a live
network is measured calendar time and nine human signatures — not engineering.

## Addendum, same day (2026-11-05) — the directive unblocked the queue

The owner then ordered: stop deferring to far-future decisions, examine everything
from git, and execute what the plan needs now. Applied the same day, with evidence:

- **Gate 0.4 closed** under the owner's explicit directive ("I approve the plan.
  Execute everything.", quoted verbatim in `params/genesis.yaml` meta.status):
  genesis parameters ratified, ADRs 0001–0004 flipped to accepted. The signature
  path remains open for the owner's signed commit.
- **Gate 0.6 applied**: saos-engine moved off the colliding :3040 to :3045 across
  params, README, docs/01, docs/09, and AGENTS.md.
- **Gate 0.2 (public half) evidenced**: scripts/census.py — 151 tracked files
  scanned, zero key material found, the sealed Actions secret verified by name;
  6 tests. The estate-side two-soul half stays estate-side (docs/10).
- **Gate 0.5 (schema half) evidenced**: params/entities/ent-001.yaml validates
  against schemas/entity.schema.json; the regulator is named (owner-via-scribe).
- **Gates 1.3 / 1.4 / 1.5 / 2.3 measured**: scripts/gate_runs.py →
  records/gate-runs-2026-11-05.md — one invoice issued → paid → anchored (chain
  ok), 4 workers accrued and paid with the trial balance balanced, 9 jobs
  settled / 5 refunded with the fraudster paid zero, and the witness band
  catching forged evidence with a full refund and zero emission.
- **The joining KPI is a measured artifact**: impl/dyn_onboard.py measures the
  reference journey (identity → funded starter → first settled job → first
  published post) at ~0.001 s offline; the live measurement repeats the same
  steps over the MCP/x402 doors once the persistent host runs (gate 1.1).
- **The founding-plan PDF still carried 69 legacy-chain mentions** — the
  representation scrub (b71211d) never reached the rendered PDF. Scrubbed at the
  generator source, regenerated (26 pp), verified 0 findings, and a CI checker
  (scripts/check_plan_pdf.py) now enforces it.
- **Gate 0.1 scanned — honestly still open**: the clearance scan
  (specs/acceptance/0.1-clearance.md) found a live same-field conflict
  (dynamisnetwork.com, "Agentic Intelligence Infrastructure") plus secondary
  users, and no token collision on CoinGecko. The gate stays open pending the
  owner's filing decision with counsel — its acceptance criterion requires "no
  unresolved conflicts", and conflicts exist.

Suite: **367 tests green** (was 291 at the audit's first writing, 249 before it, 301 when the discovery surfaces landed).

### Addendum 2 — the drill suite, completed (2026-11-05, continuation)

With the owner's standing order ("continue"), the remaining executable halves
were measured in one re-runnable command (`scripts/gate_runs.py`, twelve
drills, transcript `records/gate-runs-2026-11-05.md`): the collusion drill
(2.1 — three colluding verification records caught by independent
re-execution, refund in full), the Law-19 dashboard green over the measured
stream (2.2), the x402 paid job over real HTTP (2.4), entity #2's day-one
checklist with its own elapsed time sealed into the ledger (2.5), T2 blocked
without regulator approval (2.6), the Brier-scored calibration report (3.2),
the fleet of three with a consolidated read-only view (3.3), and the ERC-8004
export standalone (3.5). Evidence rows were also reformatted to the canonical
gate-id-first form the gate review counts — the review now shows the evidence
that exists instead of hiding it behind a formatting mismatch.

### Addendum 3 — the three open gates, their agent halves recorded (2026-11-05, continuation)

The gate review showed exactly three gates with zero evidence rows. Their
agent-executable halves are now recorded and measured, each remaining owner
act named, not claimed:

- **0.3 (agent half)** — the custody decision is recorded
  (`specs/acceptance/0.3-custody-decision.md`): the dead army — 46 dead ROT2
  WIFs (no re-key: two-soul custody forbids exporting dead key material) and
  LOST-WITH-SANDBOX accounts (re-key impossible by definition) — formally
  retired; `custom.db` (248 AES-GCM entries) stays sealed estate-side with
  zero code paths touching it; the in-repo census roster measured clean
  (158 files, 0 findings). The estate-side `CUSTODY.md` mirror and any
  on-chain disposal remain owner acts.
- **1.6 (agent half)** — the counsel packet is assembled and verified file by
  file (`specs/acceptance/1.6-counsel-packet.md`), with the verbatim ask
  (entity formation order + token-sale posture) recorded; the engagement
  letter remains a human signature.
- **3.1 (prep half)** — the witness operator runbook (`docs/20`) is verified
  as the onboarding kit candidate #1 receives: duties, bonds and slash
  conditions (`docs/11`), the one-command dry-run (four attacks rejected,
  fail-closed, measured transcript in `records/`), and the offline
  chain-verification path any third party can run. The three external
  signatures and the 14 active days remain the calendar window (docs/18
  Day 5).

Every gate in the review now carries at least one evidence row; what still
separates the project from "running" is unchanged and unchanged-sized:
calendar windows and human signatures.

### Addendum 4 — the product exists (2026-11-06)

The verdict above named the remaining mismatch honestly: the ask was a *running*
network and what existed was a tested protocol. That mismatch is now closed at
the product level. `impl/dyn_app.py` (`dyn.app.v1`) runs all five pillars as one
live application: passports with scoped capabilities (Law 3/17/18), the escrowed
work loop executing submitted code for real (four checks — runs, contract shape,
totals against independent ground truth, bounded runtime), fail-closed
settlement, the artifact-only feed with the anti-herd featured slot, sealed DMs,
the compute pool with real benchmark receipts and anti-herd allocation, and the
hash-chained ledger whose Law-19 invariant is recomputed from the app's own
actions. The console (`app/index.html`) is an operating surface, not a landing
page: every control is a protocol action, every number is read off live state.

The measured session — join → fraud attempt (check FAIL → refund, fees 0,
emission 0, on the record) → honest job (PASS → settle: 500,000,000 µ¢ settled,
200,000,000,000 DYN µ emitted, invariant holds) → post carrying the shipped
bytes → sealed DM → real benchmark, allocation and ERG settlement → chain
verification — is `records/product-session-2026-11-06.md`, produced by
`scripts/product_session.py` against the running server over HTTP only. The
suite is 338 tests green (16 new: the network driven end to end over an
ephemeral HTTP port, including the fraud path and the loop's refusal to skip
steps).

What remains between this and a hosted network is exactly what the product now
justifies asking for: a host decision and external witnesses — with something
real to host and something real to witness.

### Addendum 5 — the craft loop, adopted properly (2026-11-06)

The owner pointed the work at `storytold/craft-anything` with the direction
"use it to implement and understand it better than everyone." The engine was
studied at source level (the full study: `research/craft-anything-study.md`)
and the finding was blunt: DYNAMIS's engine was a caricature of the loop it
cited — one hardcoded task, no study step, no likeness, no refinement. That
gap is now closed: `impl/dyn_craft.py` (`dyn.craft.v1`) runs the real loop
where it pays — study captures any target (web page or file in v1) with
evidence records whose ids are content hashes (`ev_…`, `verify()`,
`carries_target_content`), the build submits real files, and the check
measures how alike the build is with craft-anything's exact contract: Dice
likeness 0..=100, claims judged one by one (a failing claim blocks readiness
however alike the rest looks), unknowns on the record (missing evidence never
counts as alike), refinement rounds (≤6) against a good-enough bar (90),
`craft.json` manifest and the capture/app/checks/inbox folder shape. The
DYNAMIS additions stay the point: the loop pays — escrow named in the
manifest, settlement through the protocol machine fail-closed on the check,
refund = fees 0 + emission 0, and the settled proof publishes as a dyn.post.v1
post carrying the shipped bytes — all on the one WorkLedger the network
already keeps.

Measured live over HTTP (`records/craft-session-2026-11-06.md`,
`scripts/craft_session.py`): a dataset job built wrong is refused with the
refund on the record; the corrected rebuild and a rebuilt web page settle at
100% likeness; the rule the engine exists to enforce is shown live — a
rebuild at 100% likeness that still fails because one claim (the title) does
not hold. The console carries a Craft panel; the suite is 361 tests green
(23 new). Remaining deltas are named, not hidden: structural (not pixel)
likeness for the web kind, two target kinds today, no human approval cards
inside the loop yet.

### Addendum 6 — the craft loop's first three deltas closed (2026-11-06)

Addendum 5 named what dyn.craft.v1 still lacked against the engine it
studied. Three of those closed the same day, each measured live
(`records/craft-session-2026-11-06.md`, `scripts/craft_session.py`):

1. **Buyer approval cards inside the loop** — the craft-anything mechanism
   that pauses a run for the person. Study opens an approval card in
   `inbox/`; the build and settlement refuse while it is open; only the buyer
   may answer it; a deny ends the loop for a refund (fees 0, emission 0); a
   late `ask_approval` (scope change) blocks an otherwise-ready settlement.
   The decision is a ledger entry (`approve`) on the same chain. Measured
   over HTTP: build while the card is open → 400 with the card's id named.
2. **Multi-page web likeness** — study crawls the start page's same-site
   routes with the reference engine's `pick_routes` rules (same origin, no
   file links, start path excluded, dash-slugs, ≤4 pages, their default
   `max_pages`), and the check compares every studied page: per-page
   likeness in the result (`pages`, their `PageLikeness` analog), the mean
   as `similarity`, and a missing route page is an unknown — missing
   evidence never counts as alike. Measured: a two-route site rebuilt with
   its routes at 100% per page, mean 100% across 3 pages.
3. **MCP parity** — craft-anything's most transferable decision ("every
   tool is both a CLI subcommand and an MCP tool") now holds for the craft
   loop: nine `craft_*` tools join the engine's seven in `dyn.mcp.v1`, the
   same actions the CLI and the console expose, with the loop's refusals
   (an open card, a skipped step) as tool results with isError=true. The
   measured flow settles through the MCP dispatch itself.

The suite is 367 tests green (6 new: approval gates, deny→refund, late card,
route slugs, missing-route block, the MCP craft flow). Remaining deltas are
named, not hidden: likeness is structural (no browser → no pixel-level
comparison), two target kinds against their breadth.
