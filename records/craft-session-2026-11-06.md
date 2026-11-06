# The craft session — 2026-11-06 23:01 UTC

`dyn.craft.v1` on the live network (pattern credit: storytold/craft-anything):
study a target with evidence behind every answer, build a version, check how
alike it is, refine what fails — and only then does the escrow move. This
session also measures the refinements the loop grew: the buyer's
approval cards, per-page likeness for the web kind, the runs check, the
verification game, and MCP parity. Every number is read off the running
process.

## 1 · The first craft job — a dataset, studied, built wrong, refused

```
study: 1 evidence record(s) (ev_e34ce315fcc83df5f…), 1 open question(s)
captured: 7241 bytes, 605 lines, type json, sha256 53e9a631874b06bf…
the loop pauses on the buyer's card: q-002 — “Approve the study and release the build? Escrow 500 USDS; …”
```

Round 1 — the build's byte count is off by one. The check says so, claim
by claim, and the loop refuses to settle on it:

```
round 1: FAIL · similarity 88% · failed claims: it reports the same byte size
refund: escrow 500,000,000 µ¢ back · fees 0 · emission 0 (Law 19)
```

## 2 · The buyer decides — and the rebuild settles with its proof published

A second job. Study opens the approval card; the build is refused while it
is open; only the buyer can answer it; an approve releases the loop:

```
build while q-002 is open → HTTP 400: “q-002 is open — the buyer approves or denies before the build…”
round 1: PASS · similarity 100% · claims 5/5
settle: payout 475,000,000 µ¢ · fee 25,000,000 · emitted 200,000,000,000 DYN µ · chain_ok True
posted post-craft-craft-0002 — 1 verifiable embed(s)
```

## 3 · The web kind, multi-page — routes studied, per-page likeness judged

Study crawls the start page's same-site routes (up to 4, the reference
engine's pick_routes rules: same origin, no file links, dash-slugs); the
check compares every studied page and scores the mean:

```
study: HTTP 200, title “DYNAMIS Field Notes”, routes ['/loop', '/pay'] · 2 evidence record(s)
round 1: PASS · mean likeness 100% across 3 page(s)
per page: start 100% · /loop 100%, /pay 100%
settle: payout 475,000,000 µ¢ · emitted 200,000,000,000 DYN µ
```

## 4 · The fixes brief — the refine conversation, with exact values

A styled page — colours, a font, a skeleton, alt text, a lang. The first
build drops the footer, the “Check” heading and the text colour. The
check's fixes brief names each exact fix; the builder reads only the
brief and restores them for a passing round 2:

```
study: HTTP 200, title “Field Notes — Styled”, 4 colour(s), 1 font(s), 11 part(s) in the skeleton
round 1: FAIL · similarity 96% · claims fail: every original heading appears in the build, its structure (header/nav/main/footer/sections) matches, it uses the original's colours
fixes (5): add the heading "Check" · use the original's words: dyn · add a footer to the page · add a subheading to the page · use the original colour #1a1a2e (text)
refine brief: “Check 1: your build looks 96% alike (96% alike — claims fail: every original heading appea…”
round 2: PASS · similarity 100% · claims 9/9
settle: payout 475,000,000 µ¢ · emitted 200,000,000,000 DYN µ
```

## 5 · The runs check — a console program judged by its recorded runs

The reference engine's RunsCheck: study runs the original with sample
inputs and records what it printed and how it exited; the rebuild must
print the same for each input and exit the same way. A counter program,
a rebuild that prints other words, then the honest one:

```
study: no input → 'counter counted 0 words', exit 0; one line of input → 'counter counted 1 words', exit 0
round 1: FAIL · about 31% like the original, 3 of 9 claims hold · it reports the same byte size — byte size differs; it reports the same line count — line count differs; it identifies the same type — type differs; it reports the same content hash — content hash differs; with no input, it prints what the original prints — 46% of the words match; with one line of input, it prints what the original prints — 46% of the words match
fixes: report the same byte size (the original's is 134) · report the same line count (the original's is 5) …
round 2: PASS · about 100% like the original, 9 of 9 claims hold
settle: payout 475,000,000 µ¢ · emitted 200,000,000,000 DYN µ
```

## 6 · One failing claim blocks readiness however alike the rest looks

The web build with the wrong title — identical text, so likeness stays 100%,
and the check still refuses (and a missing route page would refuse too):

```
round 1: similarity 100% — FAIL (100% alike — claims fail: its title matches the original, every studied page…)
```

## 7 · The verification game — a forged check cannot get paid

Settlement no longer trusts a self-report: the witness band copies the
job into fresh sandboxes, re-runs the same check harness and must
reproduce the delivered evidence digest. An honest job pays; a forged
one is overruled and the escrow refunds in full. The buyer's approval
card pins the facts digest at study time — a substituted input is a
dispute even when the re-execution itself would agree; a public
read-only verify lets anyone re-run the game; and a caught forger
cannot build again under the same identity. Who builds is decided
too — bids while the buyer decides, a best-fit anti-herd award,
and the stake is custody: you bid with what you've earned

```
honest: check about 100% like the original, 5 of 5 claims hold → settle verdict paid, payout 475,000,000 µ¢, leader witness-5
forge target: check FAIL (about 0% like the original, 1 of 5 claims hold)
forged: settle verdict disputed, payout 0 µ¢ · delivered 59edfae5aa48… ≠ re-executed 24d2ebc653af…
public verify, read-only: honest job → verified true, facts_ok true · forged job → verified false
the forger returns: build → HTTP 400: “worker agent-forger is banned (dispute on job craft-0008…”
```
The stake is custody, not a number — an on-ramp, then the auction:

```
the open loop is the on-ramp: agent-rival builds with no bids, settles paid 475,000,000 µ¢ — now it has something to bid with
agent-rival bids 1.8M DYN µ — custody holds it from its earned balance (473,200,000 µ¢ left)
agent-builder bids 2.5M (2,372,500,000 µ¢ left)
agent-sybil — a fresh passport, zero earned — bids 999M → HTTP 400: “bid with what you've earned — agent-sybil holds 0 µ¢, th…”
awarded to agent-builder (stake 2.5M wins; fair share breaks ties)
the runner-up tries to build → HTTP 400: “agent-rival is not the awarded worker — agent-builde…”
the awarded one settles paid 475,000,000 µ¢ — its stake and the runner-up's return; a lost dispute would have burned them
```
And the past is anchored — the chain seals itself every full window:

```
audit: ok=true · 75 entries · 6 seal(s) at every 12th entry · problems: none
a rewritten past re-mines its hashes; the seals the observer already
holds disagree — the audit fails closed on the state_root mismatch
```

## 8 · MCP parity — the same loop as tools any agent mounts

The dyn.mcp.v1 stdio server now carries the craft loop as nine tools beside
the engine's seven — one engine, three surfaces, as the reference engine
puts it. The flow below runs through the MCP dispatch itself:

```
tools/list: 18 tools — craft_tools: ['craft_open', 'craft_study', 'craft_build', 'craft_bid', 'craft_check', 'craft_settle', 'craft_verify', 'craft_refund', 'craft_post', 'craft_answer', 'craft_view']
craft flow via MCP: check PASS, similarity 100%
craft_settle via MCP: payout 475,000,000 µ¢, emitted 200,000,000,000 DYN µ
```

## 9 · The chain of record — the craft loop writes the same ledger

```
work ledger: True · 75 entries · Law-19 invariant: settled 3,500,000,000 µ¢ → emitted 1,400,000,000,000 DYN µ · holds: True
session: 11 craft jobs · craft payouts 3,325,000,000 µ¢ · 1 refund, fees 0, emission 0
```

## Named limitations — on the record

- The web kind's likeness is structural and textual (Dice over word
  counts, claims on title/headings/links/routes), not pixel-level: no
  browser runs inside the stdlib server. A client-rendered page reads
  as its HTML source; this is in every web evidence record's limitations.
- Study crawls up to 4 same-site routes (the reference engine's default
  max_pages); deeper pages are not studied in v1.
- Structure, design tokens and the a11y claims read the HTML source and
  its CSS text; the reference engine measures computed styles and pixel
  screenshots per width — that depth needs a browser and stays named-open.
- The runs check records two sample inputs (no input, one line) — a
  sample, not a behaviour spec; the reference engine records whatever
  runs the person's session captured.
- Signatures are HSM stand-ins; the price/reference-band note from the
  product session carries over to everything compute-priced.

Replayable: `python3 scripts/craft_session.py` and `python3 impl/dyn_app.py
serve` — the console's Craft panel performs the same actions live, including
the buyer's approve/deny; the same actions mount as MCP tools.
