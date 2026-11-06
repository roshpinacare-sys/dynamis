# The craft session — 2026-11-06 14:29 UTC

`dyn.craft.v1` on the live network (pattern credit: storytold/craft-anything):
study a target with evidence behind every answer, build a version, check how
alike it is, refine what fails — and only then does the escrow move. This
session also measures the three refinements the loop grew: the buyer's
approval cards, per-page likeness for the web kind, and MCP parity. Every
number is read off the running process.

## 1 · The first craft job — a dataset, studied, built wrong, refused

```
study: 1 evidence record(s) (ev_b6e9dcbadb5829f08…), 1 open question(s)
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

## 4 · One failing claim blocks readiness however alike the rest looks

The web build with the wrong title — identical text, so likeness stays 100%,
and the check still refuses (and a missing route page would refuse too):

```
round 1: similarity 100% — FAIL (100% alike — claims fail: its title matches the original, every studied page…)
```

## 5 · MCP parity — the same loop as tools any agent mounts

The dyn.mcp.v1 stdio server now carries the craft loop as nine tools beside
the engine's seven — one engine, three surfaces, as the reference engine
puts it. The flow below runs through the MCP dispatch itself:

```
tools/list: 16 tools — craft_tools: ['craft_open', 'craft_study', 'craft_build', 'craft_check', 'craft_settle', 'craft_refund', 'craft_post', 'craft_answer', 'craft_view']
craft flow via MCP: check PASS, similarity 100%
craft_settle via MCP: payout 475,000,000 µ¢, emitted 200,000,000,000 DYN µ
```

## 6 · The chain of record — the craft loop writes the same ledger

```
work ledger: True · 23 entries · Law-19 invariant: settled 1,000,000,000 µ¢ → emitted 400,000,000,000 DYN µ · holds: True
session: 4 craft jobs · craft payouts 950,000,000 µ¢ · 1 refund, fees 0, emission 0
```

## Named limitations — on the record

- The web kind's likeness is structural and textual (Dice over word
  counts, claims on title/headings/links/routes), not pixel-level: no
  browser runs inside the stdlib server. A client-rendered page reads
  as its HTML source; this is in every web evidence record's limitations.
- Study crawls up to 4 same-site routes (the reference engine's default
  max_pages); deeper pages are not studied in v1.
- Signatures are HSM stand-ins; the price/reference-band note from the
  product session carries over to everything compute-priced.

Replayable: `python3 scripts/craft_session.py` and `python3 impl/dyn_app.py
serve` — the console's Craft panel performs the same actions live, including
the buyer's approve/deny; the same actions mount as MCP tools.
