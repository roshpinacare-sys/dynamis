# 16 · Commonwealth executables — gates 2.5, 2.6, 3.2, 3.4, 3.5 in code

The roadmap (docs/05) left five packages that are executable in-repo — the rest of
each gate needs a funded host, external operators, or calendar time, which no amount
of code can substitute (the anti-fantasy rule). These five close the code half, with
the measured evidence commands listed in `specs/acceptance/EVIDENCE.md`.

| Module | Gate | The loop it closes |
|---|---|---|
| `impl/dyn_treasury.py` | 2.6 | treasury ops on the kernel DoA engine — decisions journaled, denials recorded, T2 blocked without the regulator |
| `impl/dyn_entities.py` | 2.5 | entity #2 instantiated from template; the ten-step day-one checklist runs and seals its digest into the work ledger |
| `impl/dyn_eval.py` | 3.2 | the evaluation market — bond-scored seats, Brier payout/burn, calibration report published with its worst bucket named |
| `impl/dyn_governance.py` | 3.4 | the amendment loop — draft → simulate → veto → execute, hash-chained, re-execution refused |
| `impl/dyn_bridge.py` | 3.5 | the ERC-8004 export bridge — discovery cards + offline-verifiable manifest, zero runtime dependency (proven by an import-isolation test) |

## 2.6 · The treasury is fail-closed to the end

`dynamis_core.policy` decides; `dyn_treasury.Treasury` executes. The separation is
the point: `execute()` **re-runs the kernel decision at execution time** — a cached
"yes" from an earlier `decide()` is never authority (TOCTOU on a treasury is closed
by construction). Approved spends book into envelope state; every outcome —
including denials — lands in a hash-chained decision journal that rehash-verifies.

The acceptance drill (the gate's own words: *"T2 spend blocked without regulator
approval — measured test"*):

```bash
python3 impl/dyn_treasury.py demo
# T2 blocked without approval — measured: {"allowed": false, "requires": "human_approval", …}
# T2 allowed with approval: spent 2500000000 µ¢, ops envelope 7500000000 µ¢ remaining
# journal verify: {'ok': True, 'rows': 2}
```

Unknown kinds are denied (fail-closed), exhausted envelopes are denied, and a
runway below the six-month floor escalates a routine T1 salary to T2 — measured in
`impl/tests/test_dyn_treasury.py` (7 tests).

## 2.5 · Entity #2 is a template instantiation

Law 20's contract (charter, DoA, envelopes, KPI tree, regulator) is carried as
`ENTITY_TEMPLATE`; `instantiate("ent-002")` produces a second managed business with
its **own** `EntityBook`, its **own** treasury state, and a canonical receipt. Entity
#1's books are untouched — the test proves the journals diverge.

The day-one checklist is ten hard checks in order (charter loaded → DoA live → book
balanced → first invoice issued → payroll envelope → T0 spend executed → T2 blocked
→ census entry → journal digest anchored into the work ledger → KPI baseline
measured). The checklist measures its own duration and seals the report digest as a
ledger `anchor` entry — "day one done" is a verifiable claim, not a story:

```bash
python3 impl/dyn_entities.py day-one ent-002     # 10 steps, measured elapsed_ms
```

## 3.2 · Evaluation is a bond-scored market

`dyn_eval.EvalMarket` seats evaluators against a bond (≥ $500), collects verdict +
confidence, then scores through the integer Brier math in `dynamis_core.brier`:
correct verdicts earn the 3% fee; wrong ones burn bond proportional to how
confidently wrong they were. The **no-embarrassment clause is code**: the closing
report includes the worst calibration bucket by mean Brier score and the market ECE,
published whatever it shows.

```bash
python3 impl/dyn_eval.py demo
# seats: 3, truth: pass, ECE 3613 bps, worst bucket 90-100 (9216 bps mean),
# burned 737200000 µ¢, fees 90000000 µ¢ — published with gaps included
```

## 3.4 · The amendment loop is veto-gated

`dyn_governance` runs draft → simulate → veto → execute over a hash-chained log.
ADR-0005's sim-first rule is executable: veto refuses an amendment with no
simulation receipt; X-class paths (custody, yield marketing, unmeasured claims)
refuse **at draft** — the loop does not even entertain them; re-execution of a
spent amendment id is refused; a veto denial stays recorded as audit trail.

```bash
python3 impl/dyn_governance.py demo
# amendment am-001: executed, canon witnesses.active now 9, log {'ok': True, 'rows': 4}
```

## 3.5 · External discovery without root dependency

`dyn_bridge` is export-only: passports in, ERC-8004-shaped discovery cards out, with
a manifest whose canonical root verifies offline. Keyrefs export as fingerprints,
never references; a passport carrying raw material is refused twice (Law 3 at
construction, again at the bridge). The import-isolation test scans every runtime
module and fails the suite if anything imports the bridge — the root runs with this
file deleted.

```bash
python3 impl/dyn_bridge.py export -        # cards + manifest, printed
```

## What still gates the phase

Code closes the loop shapes; the gates close with the world: 2.5 needs a funded
separate book and keys on a live host, 3.1 needs three external witnesses running
for 14 days, 3.2 needs real evaluators losing real bonds, 3.3 needs the fleet view.
The executables here are the contracts those operators run against — measured
drills first, world second, never the reverse.
