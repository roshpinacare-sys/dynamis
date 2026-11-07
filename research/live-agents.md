# Live agents against the real harness — 2026-11-07

The benchmark (`craft-benchmark.md`) priced seeded workers. This record
puts a live model in the worker's seat: the same pool builder
(`dyn_measure.task_pool`, seed 20261106), the same loop (open → study →
buyer approval → build → re-executed sandboxed check with its unseen
input probes → settle or full refund), the same escrow economics. Only
the delivery changes: the agent reads the buyer's request and the target
verbatim and writes the files.

## Method

- **Agent**: `z-ai chat`, model `glm-4-plus` (every reply carried the
  same model id; reply hashes ride in the record).
- **What the agent sees** (`dyn_live.brief_for`): the request, the
  target between markers, and the protocol's stated conventions — the
  lines/type definitions the approval card settles. No facts, no check,
  no probes; a test asserts the target's true sha never appears in a
  brief.
- **Scale**: the first 20 tasks of the 60-task pool — 10 file
  fingerprints, 10 web rebuilds. One pass per task, repair rate 0.
- **Pacing**: 10 s between tasks, retries with 30/60/90 s backoff on a
  rate-limited CLI. Wall-clock for the whole run: 456 s (waits
  included).

## Results

| | |
| --- | --- |
| shipped | 19 / 20 |
| refunded | 1 (full escrow back, zero fees, zero emission) |
| worker income | 3,610 M µ (payout only; the buyer's cost is payout + fee = 3,800 M µ) |
| average similarity | 988 per-mille |
| chain | audit ok, 120 entries, 10 seals |

The seeded baseline (same seed, 60 tasks, honest-and-shaky personas)
ships every working artifact at the task's own price and catches every
broken build; the live model, paid honestly, shipped 19 working
deliveries and one that the check refused — no gap between what the
buyer approves and what they receive.

## The fault the check caught (t-010, craft-0011)

A file-fingerprint report whose sha256 and byte count were perfect —
and whose other two fields were wrong in instructive ways:

1. **Line counting double-counted.** The program counted both line ends
   and line starts: on a newline byte it added one, and on the next
   non-newline byte it added one more. Any multi-line file reported
   roughly twice its line count.
2. **The type sniffer read the digest, not the file.**
   `file_bytes = sha256_hash.digest()` fed 32 hash bytes into the type
   classifier, so the type was binary noise — for every file.

The main comparison failed `lines` and `type` on the target itself; the
two unseen-input probes failed the same way, which is what separates
*computed but wrong* from *memorized* — this program really computed,
from the file it was given, and was wrong anyway. The escrow refunded
200 M µ in full; the worker earned zero from a delivery that would have
shipped under a claim-gated pipeline, because the program's own author
would have called it correct.

## The day's other findings

- **The quota hit mid-run.** An unpaced first pass (20 calls in 59 s)
  completed 20/20 shipped, then the CLI began answering 429. A
  subsequent run that hit the wall on every call measured the *rate
  limit*, not the agent — 20 empty deliveries, each honestly refunded
  by the loop. That run's record was discarded; the record here is the
  paced rerun. The lesson is structural: a worker whose call lands
  nothing must be a refund, never a crash, never a shipped guess.
- **A protocol hole, found by the model's own flakiness.** An empty
  delivery raised the engine's "an empty build claims nothing" guard —
  and left the job unbuilt, a status from which no refund existed. The
  escrow would hang forever. The engine now refunds a studied job whose
  checks history is empty (the manifest itself is the evidence that
  nothing shipped): full escrow back, zero fees, zero emission
  (Addendum 17).
- **Web rebuilds are solved when the target is in the worker's hands.**
  All ten web tasks shipped at 1000 per-mille — with the page verbatim
  in the brief, a faithful copy is a copy. The web check's real work
  begins when the target is *not* fully visible to the worker; that
  capture-independence question is the named next hunt.

## Scope

One day, one model behind one CLI, 20 tasks, one pass, no repair rounds.
This measures the protocol's effect on live builders — not model
quality, not a leaderboard. The seeded record remains the deterministic
baseline; the record: `records/live-agents-2026-11-07.json`; the
deliveries: `records/live-agents-deliveries/` (20 files, one per task).
