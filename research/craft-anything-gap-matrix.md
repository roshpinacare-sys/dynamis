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
- **Kinds**: they ship website / app / game (kinds/{website,app,game}.rs). DYNAMIS
  ships web / file — the file kind is the app kind honest to a stdlib check (it
  runs the program and compares its report claim by claim). Game and firmware:
  open, roadmap.
- **Parallel candidate builds** (`parallel: 2`, settings.rs:158): they try two
  builds and keep the more alike. Open: our escrow pays one worker per claim;
  candidates become meaningful with multi-builder auctions — roadmap, named.
- **What DYNAMIS adds that they do not have**: the loop is an economy — escrow
  named at open, fail-closed settlement through the protocol machine, Law-19
  refunds (zero fees, zero emission), buyer approval enforced by the money, a
  WorkLedger chain, and the settled proof published as a dyn.post.v1 post whose
  embeds carry the shipped bytes.

## 6 · The honest residue

What stays open after this pass, and why: pixel screenshots and layout metrics
(a browser cannot live in a stdlib-only server), computed-style design values,
console/network health, interactive states, per-width anything, game and
firmware kinds, parallel candidate builds. Each is named in the code's
limitations fields and in the session transcript — missing evidence never
counts as alike, and an unmeasured depth is a delta on the record, not a
silence.
