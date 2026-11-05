# 15 · Finance and witnesses — the SOL spine and the band behind settlement

Two roadmap packages land in-repo this chapter: the **finance spine** (gates
1.3/1.4, the SOL track the roadmap calls first-class) and the **witness band**
(gate 2.3's acceptance line). Both read and write the same objects the earlier
chapters built — the market stream, the work ledger, the engine's job folders —
so nothing here is a parallel universe. 178 tests green at the time of writing.

## 1. The hole the band closes

Settlement re-reads evidence verdicts from disk. A worker who edits an evidence
record from FAIL to PASS and flips the worklog status can make a failed build
look paid-for — and the engine, which correctly trusts its own records, pays.
`dyn_witness.forge_pass()` performs exactly that attack, in public, because an
attack you cannot reproduce cannot be defended against. The tests prove the
hole is real first (`test_the_hole_is_real_forged_folder_settles`: payout on a
forged folder), then close it.

## 2. The band: `dyn.witness.v1`

`impl/dyn_witness.py` stands 7 witnesses behind every settlement:

- **Leader selection** — VRF-ordered over the band (stand-in: deterministic
  domain-hash ranking, unpredictable in advance, recomputable by anyone; real
  VRF-over-custody-score comes with the HSM hardening, documented in-module).
- **Deterministic sampling, scaled by class** — A 5% → E 100%
  (docs/01's verification stack: sampled re-execution is the default
  instrument above deterministic checks). Nobody can pick which jobs to dodge:
  the dice were cast by (job, class, day) before the artifact existed.
- **Re-execution, not rubber-stamping** — the band copies the job folder into
  a sandbox, re-runs the *same* check harness on the hash-pinned artifact and
  inputs, and compares evidence digests. Independence comes from fresh
  execution, not reimplementation; `evidence_digest` is a fixed, documented
  projection over the fields forgery touches (verdict, artifact hash, measured
  values — not the check day, so an honest re-run on a later day reproduces).
- **The overrule** — on a digest mismatch the band invokes the engine's
  `witness_overrule` (the only PASS → FAIL path, and it requires a FAIL in the
  re-executed evidence — no proof, no overrule), then the standard fail path
  refunds the escrow in full: fee 0, emission 0.
- **Honesty about misses** — an honest FAIL re-executes to the same digest and
  passes through untouched; an unsampled job is marked "not checked this time",
  never rubber-stamped.

    $ python3 dyn_witness.py demo
    real check: checked_fail (the build is wrong)
    worker forges: 1 evidence records edited → status checked_pass
    band review: leader witness-2, sampled (class E = 100%),
      re-executed → FAIL, digests differ: 465b8188… vs c203b364…
    verdict: forged → refund in full: 500,000,000 µ¢ back, fee 0, emission 0

In the market (`dyn_market.run(..., witness=True)`), a **forger** joins the
roster and forges after a FAIL. Seed 3, ten days: 3 forged presentations,
1 caught by the band (class B samples at 10%), 2 slipped — and the forger's
earnings come **only** from slips. That is docs/07's "verification laziness"
risk measured, not hidden: light sampling misses, and the mitigation is that
re-execution is *re-runnable by anyone on any past job* (`review()` is public).
The clawback sweep over past settled jobs is the named next step.

## 3. The finance spine: `dyn.finance.v1` + `dyn.invoice.v1` + `dyn.payroll.v1`

`impl/dyn_finance.py` gives entity #1 a real double-entry book:

- **Chart of accounts** — cash, receivable; worker and verifier payables,
  deferred revenue; paid-in capital, job revenue; verification-fee,
  payroll, and worker-cost expenses. µ¢ integers everywhere (ADR-0007).
  The escrow itself is deliberately *not* an account: it is the protocol's
  object; the book sees the customer's money held (deferred revenue) and what
  settles it.
- **Hash-chained journal** — every posting is one debit account, one credit
  account, one µ¢ amount, chained like the work ledger. Same-side, unknown-
  account, zero, and negative postings are refused at `post()`, not found at
  audit.
- **Invoices** — issued at job open with the entity's markup over the escrow
  value (+20% default: the crew's share), paid on the same day, resolved at
  settle ("earned") or refund (money back to the customer). A tampered line
  breaks the invoice digest.
- **Payroll streams** — worker registry (agent → role → rate → keyref), daily
  accrual, batch payout at close: the first agent salary booked in an entity
  ledger (gate 1.4's line).
- **Anchoring** — the journal digest and the P&L digest are pinned into the
  work ledger as `anchor` entries, where the checkpoint seals pick them up:
  gate 1.3's "~$0.10 anchoring" rail, running on the chain core from docs/14.

The measured close (`book_from_market_stream` replays the same JSONL the
metrics and ledger read):

    $ python3 dyn_market.py run --days 10 --out m.jsonl
    $ python3 dyn_finance.py from-stream m.jsonl
    journal 153 postings, chain ok: True
    trial balance: dr 15,676,000,000 µ¢ == cr 15,676,000,000 µ¢ → balanced: True
    invoices: 16 earned, 10 refunded, 0 open
    payroll: 4 workers accrued 400,000,000 µ¢; payouts to workers
      4,893,500,000 µ¢ and to the band 236,500,000 µ¢, all settled at close
    P&L: revenue 5,676,000,000 µ¢ − expenses 5,130,000,000 µ¢
       = net +546,000,000 µ¢
    balance sheet identity (A == L + E + NI): True

That is entity #1's first measured P&L — revenue 5,676 USDS, net +546 USDS on
the 20% markup after crew, fees, and salaries — computed from the same stream
that proves Law 19. The tests assert the hard parts: escrow-free deferred
revenue resolves to zero, every payable settles, the identity holds, revenue
is recognized only on earned (settled) invoices.

## 4. Gate ledger, updated

| Gate | Package | Status in-repo |
|---|---|---|
| 1.3 | finance spine v1 (COA, entity book, invoicing, anchoring) | **built**; a first *real* invoice outside the sim needs the host (1.1) |
| 1.4 | worker registry + payroll streams | **built**; the first real salary payment needs the host |
| 2.1 | chain core | ledger + checkpoints (docs/14); real witness crypto remains hardening |
| 2.2 | flow-gated emission dashboard | exact invariant from the ledger; live ≥ 14-day measurement needs the host |
| 2.3 | Power Pool channels + ladder in pricing | **sampled re-execution catches the seeded fraud**; channel accounts and external witnesses remain |
| 2.4 | external rails | all three doors built; first external paid job over the internet remains |

Still deliberately not code: persistent hosting (1.1), owner ratifications
(0.4/0.5), entity #2 (2.5). Evidence files stay empty until the measurements
exist — no gate is claimed closed.

## 5. Try it

    cd impl
    python3 dyn_witness.py demo                        # forge → caught → refund
    python3 dyn_market.py run --days 10 --out m.jsonl
    python3 dyn_finance.py from-stream m.jsonl         # the entity's closed books
    python3 -m unittest discover -s tests              # 178 checks, keep green
