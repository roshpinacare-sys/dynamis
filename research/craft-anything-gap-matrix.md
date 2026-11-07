# The craft-anything gap matrix — the serious comparison

Compared: `storytold/craft-anything` at HEAD (the ArtCraft rebuild engine) against
DYNAMIS's `dyn.craft.v1` (impl/dyn_craft.py), mechanism by mechanism, with both
sides cited. Written after reading their check pipeline in full
(`crates/ai/src/rebuild/kinds/website.rs`, 877 lines) — not their README. Status
vocabulary: **parity** (same mechanism, same formula), **adapted** (their
mechanism at the depth a no-browser study can reach, difference named),
**open** (named, with the reason it stays open). DYNAMIS side: `dyn_craft.py`
function names; their side: `file:line` in the upstream repo.

---

## 1 · The loop and its contract

| Mechanism | craft-anything | DYNAMIS | Status |
| --- | --- | --- | --- |
| A job is a folder | `craft.json` + `capture/` + `app/` + `checks/round-N/` + `inbox/` (workspace.rs) | same shape, plus `evidence/` and `post/` | parity+ |
| Steps the person sees | `Step::{Study, Build, Check, Done}` (workspace.rs:195) | `step`: study → build → check → ready in the manifest | parity |
| Run status | `Status::{New, Inspecting, Building, Checking, NeedsYou, Ready, Stopped}` (workspace.rs:166) | steps timeline records the same vocabulary (`_step`); manifest `status` is the money-state machine | adapted (ours carries the escrow states too) |
| Refinement rounds | `max_rounds: 6` (settings.rs:148) | `rounds: {done, max}` default 6, refuse beyond | parity |
| Good-enough bar | `good_enough: 90.0`, claim gating at `mod.rs:809` | `good_enough` manifest field, default 90, gates `passed` | parity |
| Waiting for the person | `Status::NeedsYou`; Ask(Request) cards | approval cards in `inbox/`, buyer-only, deny ends for a refund | parity+ (ours is enforced by the escrow) |
| Decisions read fields, not prose | CheckResult contract (workspace.rs:220+) | same contract: `passed`, `similarity`, `claims`, `unknowns`, `note` for people | parity |
| Everything written atomically | `project::write_atomic` (used at study.rs:199) | `_atomic` on manifest, facts, routes, inbox, checks, post, evidence | parity |

## 2 · What study captures

| Their capture (measured DOM, a real browser) | Ours (HTTP + HTML source) | Status |
| --- | --- | --- |
| Screenshot per width — `web_widths [1440, 768, 390]`, filtered to 320..=3840, ≤4 (settings.rs:165) | none — no browser in a stdlib server | **open** (named: pixel depth) |
| Layout metrics per width: `page_w`, type sizes, blocks with `pad`, `per_row`, `column` (design_notes/block_diffs, website.rs:519-626) | none measurable without layout | **open** |
| Outline → `skeleton`: the page's parts in document order, roles counted (PARTS, website.rs:275-297) | same 20-part PARTS table, parsed from source HTML (`_Page.skeleton`) | **adapted** — same vocabulary, source depth |
| Text + headings per page and route; routes via `pick_routes` rules, ≤4 (`study.rs:184`, website.rs:73-124) | identical rules: same origin, no file links, dash-slugs, one level deeper, ≤4 (`_study_routes`) | parity |
| Design values from computed styles: backgrounds, text colors, fonts, font sizes, spacing (design_values, website.rs:510) | design tokens from CSS text: colours by role, font stacks, px sizes (`design_tokens`) | **adapted** — CSS-text depth, named in the evidence record |
| Console health + a11y: errors, failed requests, landmarks, unnamed controls, alt text, `lang` (health_notes, website.rs:385-414) | what the source shows: `images_without_alt`, `lang` (`_Page`) | **adapted** — the rest needs a browser |
| States: menus/pop-ups pictured and paired (`pair_states`, website.rs:660+) | none | **open** |
| Console runs recorded: per input, what it printed and how it exited (`RUNS_BRIEF`, app.rs:11; capture in runs.rs) | sample runs for Python originals: `craft_run_capture`, two inputs (no input, one line), stdout + exit recorded in `capture/facts.json` | **adapted** — two sample inputs, not a behaviour spec |

## 3 · The check, claim by claim and note by note

Their design principle, read off the code: **claims decide, notes guide** —
`page_claims` (website.rs:449) makes only four claims; text/structure/design are
notes ("they guide the builder but don't change the score", website.rs:718).
DYNAMIS has no screenshots, so its text claims carry the score; the new layers
keep their split: hard claims for what the source proves, notes for guidance.

| Their check layer | Their formula | Ours | Status |
| --- | --- | --- | --- |
| Text likeness | Dice over word counts, 2+ chars: `200·shared/(a+b)` (text_likeness, website.rs:268) | identical (`alike`/`words`), including the 2-char rule | parity |
| Missing headings | ≤8, page order (TextLikeness) | `missing_headings` ≤8, into claims + fixes | parity |
| Missing frequent words | ≤12, most frequent unused (TextLikeness) | `missing_words` ≤12 (`missing_words()`) | parity |
| Title / links | title equality; link count within 25% | same claims | parity |
| Structure | skeleton `200·common/(a+b)`, missing parts ≤6 (structure_likeness, website.rs:348) | same formula + PARTS; claim fails when a whole part kind is gone or below 80 (`skeleton_score`) | adapted (theirs is a note; ours is a claim because text is our only hard evidence) |
| Colours | missing by role, ≤6, `same_colour` ±3/channel (website.rs:495-527) | `same_colour` port; claim on the original's colours, ≤6 in detail | adapted (source CSS vs computed) |
| Main font | first family of the stack, next/font unwrapped (family, website.rs:502) | `family()` port; claim on the main font | adapted |
| Text sizes / spacing / padding / per_row / column | per-width diffs, ±2-8 px tolerances (block_diffs, website.rs:566) | sizes as a note; the rest **open** (needs layout) | open |
| No sideways scroll | claim per width (page_claims, website.rs:456) | **open** (needs a viewport) | open |
| No new console errors / failed requests | claims (page_claims:465-473) | **open** (needs a browser) | open |
| Landmarks | claim (page_claims:474) | **open** | open |
| Pictures without alt | health note, "worse than the original" (health_notes:404) | hard claim, same direction (`built > original` fails) | adapted |
| Page language | health note (health_notes:409) | hard claim when the original sets one | adapted |
| Per-page likeness | PageLikeness per route + mean of screenshots (WebVisualCheck:775-790) | `pages[]` per route + mean of text likeness | adapted |
| States claims | per-control claims (states_note:679) | **open** | open |
| Recorded runs: same input → same output | RunsCheck, Dice ≥ `OUTPUT_ALIKE 80` over output words with both program names → "program" (runs.rs:150-190) | identical formula and normalisation (`output_words`), 2 sample inputs | **parity** |
| Exit parity | "With {name}, it {exits with code N} like the original" (runs.rs:176) | same wording (`run_how`), timeout = still running | **parity** |
| Round summary for people | self_check::summary: "about 93% like the original, 5 of 5 claims hold" (self_check.rs:64-73) | `result["summary"]`, same format | **parity** |

## 4 · The refine conversation

| Theirs | Ours | Status |
| --- | --- | --- |
| `refine()` prompt with exact values: "fix the padding, items per row, sizes, colours and fonts the check names at each width with the exact values it gives" (website.rs:195) | `refine_brief` on every failing round: "Fix, biggest differences first: …" from the fixes list | parity in spirit, values from our layers |
| Builder replies "1-2 plain sentences on what you changed" | `build(statement=…)` recorded per round in `statements` | parity |
| Structured fixes data: missing headings/words/parts, colour and font names | `fixes: [{code, message}]` — machine-readable, applied by a builder that reads nothing else (measured live: section 4 of the session transcript) | parity+ |

## 5 · Surfaces, kinds, and what DYNAMIS adds

- **Surfaces**: their "every tool is a CLI subcommand and an MCP tool" — DYNAMIS
  runs one engine behind three surfaces: `dyn_craft` CLI, `dyn_app` HTTP/console
  (including the buyer's approve/deny), and 9 `craft_*` tools in `dyn.mcp.v1`
  beside the engine's 7. Parity.
- **Kinds**: they ship website / app / game (kinds/{website,app,game}.rs). The
  app kind's four checks (app.rs:55-58) map as: BuildCheck → our report claims;
  **RunsCheck → our runs layer, ported claim-for-claim**; ScreenshotCheck →
  open (pixels); MechanicsCheck (Deep-mode decompile) → open, roadmap. The
  game kind's checks (game.rs:152-159: BuildCheck, ScreenshotCheck,
  SelfTestCheck, MechanicsCheck, CreditsCheck) are not ported. DYNAMIS ships
  web / file.
- **Parallel builds** (`parallel: 2`, settings.rs:158): read properly, this is
  the RunSet limit — how many *different projects* build at once
  (tools.rs:19: "Up to `build.parallel` projects build at once (2 by default);
  more are queued"), not candidate builds of one target. DYNAMIS's engine
  serves one network at a time; multi-project concurrency is an operator
  concern, not a protocol one. (An earlier draft of this matrix misread this
  as candidate builds — corrected after reading tools.rs and runs.rs.)
- **What DYNAMIS adds that they do not have**: the loop is an economy — escrow
  named at open, fail-closed settlement through the protocol machine, Law-19
  refunds (zero fees, zero emission), buyer approval enforced by the money, a
  WorkLedger chain, and the settled proof published as a dyn.post.v1 post whose
  embeds carry the shipped bytes.

## 6 · The engine loop, ported

| Their loop behaviour | Where | Ours | Status |
| --- | --- | --- | --- |
| Rounds break at `max_rounds`, then the run fails with "The build isn't working yet. {why}" and a remediation (mod.rs:868-900) | same refusal, same shape: the enriched error names the round cap and points the buyer at the refund | parity |
| The person's summary line on the ready state (mod.rs:897-899) | the check's `summary` field, their exact format | parity |
| A build that claims work but wrote nothing: "app/ has no files yet, so the builder hasn't written the project" (#736, website.rs:730) | empty `files` refused at build() with the same citation; both checks' no-program notes carry the same prefix | parity |
| `refine()` sends the builder back with exact values + "reply with 1-2 plain sentences on what you changed" (website.rs:195) | `refine_brief` + `statements[]` per round | parity |

## 7 · Divergence by design — the band reaches the craft loop

Their witness band (dyn_witness.py) already runs sampled re-execution with a
seeded forge attack (`forge_pass`) — over their *engine* demo jobs. Our craft
loop's settle had been passing `reexec_matches=True` as a constant: the band
existed, the craft loop didn't call it. Closed:

- `craft_evidence_digest` — the documented projection a settlement stands on
  (check id, verdict, per-mille likeness, every claim's title/passed/detail,
  the person's summary line); round numbers, timestamps and runtime are
  deliberately out, so an honest re-execution on a later day reproduces it.
- `craft_reexecute` — the VRF-stand-in leader plus witnesses each copy the
  job into a fresh sandbox, reinstate the status and re-run the SAME check
  harness; determinism makes agreement the only honest outcome.
- `craft_verify(delivered_digest=…)` — the submitter's own digest (from
  memory, what it asks to settle on) against the disk truth. Found by the
  live session harness and fixed: a digest compared disk-against-disk let an
  in-memory forgery pay; comparing the submitter's claim to fresh execution
  catches forgeries on either side.
- On mismatch: verify_fail → DISPUTED → resolve_budget (the burden is on the
  worker) → escrow refunded in full, the job back to checked_fail, a
  `dispute` entry on the chain ledger. Measured in the session transcript §7:
  honest → paid (leader witness-5); forged → disputed, payout 0, two
  different digests printed on the record.

Also this pass: the measurer itself is tested — a seeded mutation battery
proves the likeness function bounded, sensitive to one changed word and
ordered by severity; manifest writes are fsync'd write-then-rename (a torn
write leaves the old record intact); ledger entries carry Merkle inclusion
proofs with sides preserved, verifiable against the root without the ledger.

The game then grew roots, teeth and eyes: the buyer's approval card pins the
facts digest at study time, so a substituted input is a dispute even when the
re-execution itself would agree (the pin binds the inputs; the sandbox binds
the execution); `POST /api/craft/{id}/verify` and a `craft_verify` MCP tool
re-run the whole game read-only — verification is re-runnable by anyone, not
a settlement-time event; and a worker with a dispute on the chain's ledger
cannot build again under that identity. The honest boundary: wallets in this
rail are per-kit ephemeral, so the teeth are access control, not stake; and
the ban binds the passport, so sybil resistance is the identity rail's job,
not the craft loop's.

The auction closed the last structural gap in the loop's head: who builds
was whoever called build. Now workers bid while the buyer holds the
approval card — price and stake on the record, one bid each, bids above the
funded escrow refused (the escrow pays, not a promise), and a caught forger
cannot even bid. On approve, the award picks best-fit anti-herd with the
compute scheduler's key ported to craft: strongest stake, then fair share
(fewest settled builds on this chain), then canonical id — never the
cheapest, never the loudest, and every ranking input is on the record so
the award is auditable. The build gate binds the winner: only the awarded
worker builds, across refine rounds too; a job with no bids stays open,
exactly as before.

The stake became custody, and the teeth got an economy. A bid's stake is
no longer a figure a fresh passport types — it is held from the bidder's
rail balance at a documented peg (1 DYN µ ↔ 1 µ¢, a stand-in for a market
price, like the VRF stand-in for a VRF), so you bid with what you've
earned: a fresh passport with a zero balance cannot outbid with numbers.
Balances start at zero and grow only from honest settles — the open loop
(no bids needed) is the on-ramp that earns the right to compete. A paid
settle returns the winner's stake and every losing bidder's; a refund
returns them all; and a lost dispute burns the stake — the caught forger
doesn't just lose access, it loses money. The dispute entry now carries
the signer's keyref and the ban lookup matches identity or key, so a kit
that maps many ids to one key cannot wash the ban by renaming. The
boundary is still named honestly: a fresh keypair with freshly earned
balance is a new worker, and the MCP surface stays custody-free (the app
is the custody layer; the loop is the protocol).

And the past is anchored. The checkpoint machinery existed from the start
— windows of twelve entries sealed with a BFT witness threshold — but
nothing sealed the craft chain and nothing verified the seals: an anchor
nobody takes or checks is decoration. Now the ledger seals itself through
a hook the moment a full window completes, the app keeps every seal, and
`GET /api/audit` re-verifies chain, emission invariant, seal coverage and
every seal — fail closed. The teeth are measurable: a rewritten past that
re-mines all its hashes passes `verify_chain` alone, and still fails the
audit, because the seals the observer already holds disagree on the state
root. The signatures became real. The band signs with ed25519 — RFC 8032
implemented in pure python inside dynamis_core (stdlib-only per ADR-0007,
pinned to the RFC's own test vectors and cross-checked against
OpenSSL-backed keys), each seal domain-separated over height and state
root, verified only against the pubkeys an observer pinned when the band
formed; an unpinned band verifies nothing, a forged signature fails
closed, and the BFT threshold still binds. The boundary moves to where it
truly lives: key custody. In the kit the band is in-process — the app
holds its own seeds, so the app could re-sign; in production the keys sit
in independent witnesses' HSMs and no single re-miner has them. The
cryptography, the threshold and the fail-closed verification are already
the protocol's; what remains is the trust geometry, named and honest.

## 8 · The benchmark — what the loop changes, measured

The loop's promise was never that agents get smarter; it is what survives
to the buyer, at what cost, and who earns. That is measurable without
claiming anything about model quality: `impl/dyn_measure.py` runs the same
seeded deliveries through three pipelines — naive (pay everything, verify
nothing), self-report (the worker's claim gates), craft (study, build,
re-executed check, settle or refund) — over a 60-task pool of file
fingerprints and web rebuilds served on a real HTTP server, and reads the
money from the delivered rows with conservation asserted in code. The
numbers (seed 20261106, 12,000 USDS pool value, 30% broken builds, 11
forged claims): naive and self-report ship all 20 broken deliveries and
catch no forged claims at 300 USDS per working artifact; craft ships zero,
catches all 11, refunds 4,000 USDS and lands at the task's own 200 USDS
price — while the honest worker earns 8,000 USDS and the shaky one earns
zero. Overhead, measured on the same run: 175 ms per full job, the chain
sealed itself 30×, audit ok. The benchmark earned its keep on its first
run: a broken build leaked through the web check because **injected
scripts are invisible to text likeness** — the parser rightly skips script
content, so a hostile `<script>` scored 100% alike and no claim existed to
catch it. The harness now captures the original's scripts (count + srcs)
and asserts "no scripts the original doesn't have"; the leak is pinned as
a test and the faithful copy still passes. The honest scope is stated in
`research/craft-benchmark.md`: this measures the protocol's effect under a
stated generation-error model over real loop paths and real money — not
model quality. Measuring real agents against this pool is the named next
measurement; the harness they would face is the same one these numbers
came from.

## 9 · The honest residue

What stays open after this pass, and why: pixel screenshots and layout metrics
(a browser cannot live in a stdlib-only server), computed-style design values,
console/network health, interactive states, per-width anything, game and
firmware kinds, Deep-mode mechanics sheets — and the runs layer's own
limitation: two sample inputs are a sample, not a behaviour spec, which the
runs evidence record states on its face. Each is named in the code's
limitations fields and in the session transcript — missing evidence never
counts as alike, and an unmeasured depth is a delta on the record, not a
silence.
