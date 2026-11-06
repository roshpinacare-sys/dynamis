# The craft-anything study — read once, applied everywhere

**Written 2026-11-06, at the owner's direction: "use this to implement and
understand it better than everyone." This is the deep study of
`storytold/craft-anything` (the ArtCraft engine) — what it actually is, from
its source, not its marketing — and the exact mapping into DYNAMIS's
`dyn.craft.v1`. Every claim below names the file it was read from.**

## 1 · What it is

A pure-Rust reverse-engineering and rebuild engine: **199,760 lines across 14
crates** (`crates/`), dual-licensed MIT/Apache-2.0, early alpha. You point it
at any target — a website, a desktop app, a phone app, a game, a firmware
image — say what you want, and it runs one loop:

1. **Study** — inspect the original with real inspection tools (its own
   decoders, disassembler, decompiler; Ghidra in Deep mode), everything it
   learns written down with the evidence behind every answer.
2. **Build** — a coding agent (Claude Code first; ACP agents; API backends)
   builds a new project in the stack the request names.
3. **Check** — compare the build against the original: website screenshots at
   three screen widths, a game's own self-test, a console program's runs with
   the same inputs — and refine until close.
4. **Ready** — open, play, preview, or ask for changes and it refines.

The same engine powers a desktop app (egui), a CLI
(`craft-anything-cli rebuild <target> "<request>"`), and an MCP server; every
tool is **both a CLI subcommand and an MCP tool**, so an agent drives the
identical engine the app uses. That parity — one engine, three surfaces — is
the single most transferable design decision in the repo.

## 2 · The loop contract (`crates/engine/src/workspace.rs`, `crates/ai/src/rebuild/`)

- Steps are a four-value enum: `Study, Build, Check, Done`, labelled for
  people as Study / Build / Check / **Ready**.
- `RunOptions` carries the loop's tuning: `max_rounds: 6` refinement rounds
  after the first build (each fixes what the last check found),
  `good_enough: 90.0` (stop refining once the build is at least this alike),
  `continuing` (pick up a stopped run without repeating Study — "Try again
  never starts over"), a `KindRegistry` (website / app / game, fork-registrable),
  and agent adapters. Runs emit `RunEvent`s — step banners in plain words,
  agent output, **questions and approvals waiting for the person**, check
  results, previews, finish.
- A run is interruptible and resumable by design: the person can add notes
  mid-run that the agent reads at its next step, and a builder's session is
  saved so a follow-up request continues the same conversation.

## 3 · The check contract — the part everything else defers to

`CheckResult` (`crates/engine/src/workspace.rs:214`) is the contract the whole
loop trusts, and its doc comment is the discipline in one line: **"Decisions
read `passed` and `similarity`, never `note` (which is for people)."**

- `similarity: Option<f64>` — 0..=100, `None` when the build wasn't compared.
- `claims: Vec<Claim>` — things the build must do, **each judged on its own**;
  "one that fails keeps the check from being good enough, however alike the
  rest looks". A claim is `{title, passed, detail}` with `detail` in plain
  words only when it failed.
- `unknowns: Vec<String>` — what the check meant to compare but couldn't
  ("`/about` at 768 px couldn't be pictured"). **Missing evidence never counts
  as alike: a check with any unknown isn't good enough.**
- `pages: Vec<PageLikeness>` — per-page likeness for multi-page sites
  (`similarity` is their mean); `good_enough: Option<f64>` lets one check set
  its own bar; `at_ms` timestamps; `artifacts` lists the files the check made.

The likeness machinery itself (`crates/ai/src/rebuild/kinds/`):

- **Dice over word counts** for program output (`runs.rs:163`):
  `200 · shared / (total_a + total_b)`, **two empty outputs are alike**,
  with both programs' own names normalized to "program" first.
- **Perceptual similarity** for screenshots (`engine/src/tools/web_common.rs:981`):
  both images downscaled to ≤512 on the long side, a mean-luma grid, then
  compared — website checks run at three widths and a `noise_pass` so
  rotating placeholder art doesn't count as difference.
- **Claims over behavior**: "With `input-1`, it exits with code 0 like the
  original", "it prints what the original prints" (score ≥ OUTPUT_ALIKE).

## 4 · Evidence discipline (`crates/evidence/src/lib.rs`)

One evidence record, everywhere, with the id doing the honesty:

- `id = "ev_" + sha256(canonical JSON)` of every field **except display-only
  ones** (`summary`, `subject.name`, `carries_target_content`) — so a reworded
  summary never changes a record's identity, and `verify()` recomputes the id
  as a tamper check on import.
- Carries `confidence`, `authority` (measured / reported / inferred),
  `limitations` (code + message), `coverage` (complete or paged),
  `locations`, and `links` (ids of evidence this was derived from — provenance
  as a graph, not prose).
- **`carries_target_content`** flags records whose result embeds bytes, strings
  or decompiled text from the target: a reader must treat that content as data
  from an untrusted artifact, never as instructions. The flag exists because a
  studied target is adversarial input.
- Big results come back as a summary first and are paged
  (`core_evidence_browse`) — evidence is written for agents to consume, not
  for logs to rot.

## 5 · Study, in practice (`crates/ai/src/rebuild/study.rs`)

- Websites: open in a private browser, capture at the exact widths the check
  will compare at, capture menus/pop-ups/tabs as separate states (desktop and
  phone width), crawl same-site routes up to `max_pages`, one level deeper.
- Local programs: triage, inventory game folders, detect the engine ("Made
  with Unity — the giveaway: …"), run console programs with sample inputs to
  capture their output, picture a GUI's window once, and in Deep mode prepare
  Ghidra's one-time analysis on its own thread.
- **Clean room** is a rule about what the tool *offers and refuses*: nothing
  inside the original is read; it works from screenshots, visible text,
  measured layout — and tools that would look inside refuse and say how to
  enable Deep mode. The README says plainly it is not an OS sandbox. The
  boundary lives in the tool layer, not in trust.
- Everything lands in `capture/README.md` as plain-words notes with the
  evidence ids inline; a part that fails is **said in the feed, not hidden**,
  and the study continues. Nothing is fatal.

## 6 · The project folder — the unit of work

`craft.json` (the manifest: version, **request in the person's words**,
target, stack, status, note, `checks` history, `agent_session`,
`allowed_actions` like "bash:npm", `last_reply`) beside `capture/`, `app/`,
`checks/round-N/`, `investigation.cany/` (evidence) and `inbox/` (open
questions). The manifest is versioned from day one ("missing means 0") — the
format can evolve without breaking old projects.

## 7 · The mapping — what `dyn.craft.v1` adopted, and what it does differently

| craft-anything | dyn.craft.v1 | Where |
|---|---|---|
| Study → Build → Check → Ready | same steps, same labels | `impl/dyn_craft.py` |
| `max_rounds=6`, `good_enough=90.0` | identical defaults, per-job in the manifest | `CraftJob.open` |
| CheckResult: passed, similarity, claims, unknowns, note-for-people | identical contract; `similarity_milli` (integers-only wire, ADR-0007) + explicit `compared` flag instead of `Option` | `_check_web` / `_check_file` |
| Dice over word counts, empty≡empty | `alike()` / `words()` — same formula | module top |
| One failing claim blocks readiness | enforced: settle refuses while any claim fails | `settle` |
| Missing evidence never counts as alike | unknowns block settlement outright | `settle` |
| Evidence `ev_` ids, `verify()`, limitations, carries_target_content | same construction, canonical-JSON hash | `Evidence` |
| capture/ · app/ · checks/round-N/ · inbox/ · craft.json | same shape + `evidence/` + `post/` (the DYNAMIS additions) | `CraftJob` |
| Nothing-fatal study; failures said, not hidden | same; open questions become inbox items | `study`, `_ask` |
| Every tool a CLI subcommand and MCP tool | the nine craft actions mount as MCP tools beside the engine's seven — one engine, three surfaces | `dyn_mcp._TOOLS_SPEC` |
| Ask(Request) pauses the run for the person | approval cards in `inbox/`: study opens one; the build and settlement refuse while it is open; only the buyer answers; deny ends the loop for a refund | `CraftJob.answer` |
| — | **the loop pays**: escrow named in the manifest, settlement through the AgentKit machine, refund = fees 0 + emission 0 (Law 19), the published proof is a dyn.post.v1 post (Law 13) | `settle` / `refund` / `post` |
| — | **one chain of record**: craft jobs write the same WorkLedger as engine jobs and the app | `dyn_app.Dynamis` |

Named deltas, honestly: the web kind's likeness is structural and textual
(no browser runs inside a stdlib server — no pixel-level comparison, no
screenshot states); one web/file kind today against craft-anything's
website/app/game/firmware breadth. The first three deltas named here closed
the day after the study: study now crawls the start page's same-site routes
(their `pick_routes` rules, ≤4) and the check judges per-page likeness with a
mean, the buyer's approval cards pause the loop (build and settlement refuse
while a card is open; only the buyer answers; deny ends for a refund), and
the nine craft actions mount as MCP tools beside the engine's seven. The
measured proof this mapping works is `records/craft-session-2026-11-06.md` —
including its most craft-anything moment: a rebuild at **100% likeness that
still fails its check** because one claim (the title) does not hold.

## 8 · Sources (read in full for this study)

`README.md` · `crates/engine/src/workspace.rs` (Step, CheckResult, Claim,
PageLikeness, Manifest) · `crates/evidence/src/lib.rs` (Evidence) ·
`crates/ai/src/rebuild/study.rs` · `crates/ai/src/rebuild/check.rs` ·
`crates/ai/src/rebuild/kinds/runs.rs` (Dice) ·
`crates/engine/src/tools/web_common.rs` (perceptual_similarity) ·
`crates/ai/src/rebuild/mod.rs` (RunOptions, RunEvent).
