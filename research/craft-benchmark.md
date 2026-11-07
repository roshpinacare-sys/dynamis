# The craft benchmark — method, numbers, scope

*records/benchmark-2026-11-06.{json,md} · impl/dyn_measure.py · 2026-11-06*

## The question

The loop's promise was never "agents get smarter". It is: **what survives
to the buyer, at what cost, and who earns**. That is measurable without
claiming anything about model quality — run the same deliveries through
pipelines that differ only in verification, and read the money.

## Method

- **Pool**: 60 tasks, seed 20261106 — 30 file-kind fingerprint reports
  (dataset → sha256/bytes/lines/type, byte-exact) and 30 web-kind faithful
  rebuilds (three doc pages served over a real HTTP server; the loop's
  study fetches them the way it fetches any live site, and the build must
  include every studied route).
- **Worker model (stated, not hidden)**: 30% of builds ship broken
  (deterministic draws: off-by-one line counts, truncated hashes, wrong
  types; swapped titles, dropped headings, injected scripts), 50% of those
  claim "it is correct". Repair rate 0. The draws are a function of the
  seed alone — anyone can recompute every number.
- **Pipelines over the same draws**:
  - *naive* — pay every delivery, verify nothing;
  - *self-report* — the worker's claim is the gate (nothing re-executes);
  - *craft* — the real loop: open → study → approval card → build →
    re-executed check → settle or full refund.
- **Money** is read from the delivered rows (settle carries payout + fee,
  refund carries escrow_back), with conservation asserted in code:
  paid + refunded == pool value in every honest run.

## Results (60 tasks, 12,000 USDS pool value)

| pipeline | shipped broken | working | buyer paid | refunded | cost/working | forged caught |
| --- | --- | --- | --- | --- | --- | --- |
| naive | 20 | 40 | 12,000 USDS | 0 | 300 USDS | 0 |
| self-report | 20 | 40 | 12,000 USDS | 0 | 300 USDS | 0 |
| craft | **0** | 40 | 8,000 USDS | 4,000 USDS | **200 USDS** | **11/11** |

Overhead, same run: 175 ms per full job; the chain sealed itself 30× over
360 ledger entries; `GET /api/audit` → ok=true.

## The finding the benchmark was for

The first run leaked a broken build through the web check: **injected
scripts are invisible to text likeness** — the parser rightly skips
script content, so a page with a hostile `<script>` scored 100% alike
and no claim existed to catch it. The harness now tracks scripts
(count + srcs) in the capture and asserts "no scripts the original
doesn't have"; the benchmark's own leak test pins the claim, and the
faithful copy still passes. A benchmark that only confirms what you
built is decoration; this one was allowed to break something, and did.

## Scope, honestly

- The workers are seeded draws, not agents: this measures the
  **protocol's** effect under a stated error model, not model quality.
  Measuring real agents against this pool is the named next measurement,
  and the harness they would face is the same one these numbers came
  from.
- The check harness is re-execution against independently captured
  facts — it is exactly as strong as the facts' independence. For file
  tasks the facts are content-addressed (byte-exact); for web tasks they
  are the studied page's own tokens. Adversarial research against the
  capture is the honest next hole to hunt.
- Determinism: pool, draws, verdicts and every µ¢ are a function of the
  seed; wall-clock overhead is the only reported number that varies.

## Hardening, one day later (2026-11-07)

Two attacks were then aimed at the file-kind check, and both were real:
a program that memorizes the target's answers passed the original
comparison, and a program that read its expected answers from the job's
own capture passed with zero work. The harness now runs every execution
in a disposable sandbox and judges two unseen inputs per round (their
truth computed with the capture's own rules); the report kind's honest
builders — including this benchmark's own — turned out half-memorized
under the new probes and were made to compute. The record above still
reproduces exactly after the hardening (every non-overhead field
identical at seed 20261106); the honest price is 175 → 241 ms per job.
Method note unchanged: the protocol's effect, not model quality.
