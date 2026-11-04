# Test plan — what "verified" means at every gate

Evidence discipline: a package closes only with a line in `specs/acceptance/EVIDENCE.md`
(command, exit code/hash, date). This file maps each gate to the drills that produce
that evidence. Nothing here is self-attested; every drill emits a receipt or a log.

## 1. Continuous (every phase, from day one)

| Drill | Cadence | Pass line | Tooling |
|---|---|---|---|
| impl unit suite | every commit | 61/61 OK, zero skips | `python -m unittest discover -s tests` (impl/) |
| sim regression | every economy-relevant change | Law-19 invariant exact; Law-9 margin ≥ 0 all seeds; treasury solvent | `python sim/simulate_economy.py` → results/summary.json |
| schema validity | every schema change | all 7 schemas draft-2020-12 valid + examples validate | `jsonschema` check (schemas/) |
| census patrol | 15/50-min beats (estate pattern) | zero plaintext keys on disk; census exits 0 | `custody-census` |
| kill-switch drill | monthly | every service's kill switch arms and halts within 60 s | per-service runbook |

## 2. Per-gate drills

### Gate 0 (Ignition)
- **0.2/0.3 custody**: census run exits 0; device scan finds zero plaintext keys;
  `CUSTODY.md` roster matches census roster exactly.
- **0.4/0.5**: `params/genesis.yaml` parses; `params/entities/ent-001.yaml` validates
  against `schemas/entity.schema.json`; DoA matrix validates against
  `schemas/doa.schema.json`.

### Gate 1 (Spark)
- **1.1 uptime**: engine + HSM + economy ≥ 99% over 7×24 h measured by the heartbeat
  history, not by claim.
- **1.2 benchmarks**: ≥ 3 devices tiered per specs/benchmarks.md §2; tier table published
  with receipt hashes.
- **1.3 invoice-to-settlement**: one real invoice issued from entity #1's book, settled,
  digest anchored (~$0.10 notary receipt).
- **1.4 payroll**: one agent salary paid as a USDS stream, booked as the salary event
  kind in the entity book.
- **1.5 escrowed job alpha**: first internal job walks the full state machine
  (state-machines.md §2) with a hash-chain-verified event log.

### Gate 2 (Grid)
- **2.1 collusion drill (seeded)**: three colluding workers submit identical fraudulent
  claims; sampled re-execution catches ≥ 1; dispute resolves to refund; bonds burn;
  the event log proves it. *Seeded fraud is a test fixture, announced as such.*
- **2.1 witness failover**: kill one active witness; standby promotes within one seal
  (36 s); no checkpoint gap > 2 seals.
- **2.2 emission dashboard**: 14 consecutive days where `emitted == revenue-verified`
  (the invariant, rendered public — Law 8).
- **2.3 seeded capacity fraud**: a device advertises T-GPU2, delivers T-NONE; spot
  check drops its tier; slashing recorded; pool advertising shrinks the same day.
- **2.4 x402**: an external machine client (no root credentials) pays and completes a
  job end-to-end; the root's books show the flow without any root key exposure.
- **2.6 DoA enforcement**: a scripted T2 spend attempt without approval is blocked and
  logged; with approval it passes; an X-class attempt is blocked at any approval level.

### Gate 3 (Commonwealth)
- **3.1 external witnesses**: ≥ 3 external operators active ≥ 14 days under VRF+bonds.
- **3.2 calibration report**: evaluators' Brier/ECE published per calibration_bucket;
  the no-embarrassment clause honored — gaps shown as found (Law 8).
- **3.4 amendment loop**: one charter amendment executed via ADR + regulator veto keys,
  with the DoA diff reviewed against `schemas/doa.schema.json`.
- **3.5 exit drill (Law 21)**: ERC-8004 bridge disabled; external discovery halts;
  books, custody, identity unaffected — measured, not asserted.

## 3. Chaos fixtures (the fleet's own history, made reproducible)

| Fixture | Reproduces | Expected outcome |
|---|---|---|
| sandbox-wipe | the fleet's four wipes/month | every component boots from chain/sealed state; nothing human-recoverable |
| stranded-keys | 2026-10-21 incident | census flags before any value path touches them |
| herd-burst | Steem vote-herd pattern | anti-herd schedule + caps hold; Sybil signature flagged |
| price-feed spoof | witness outlier | medianizer flags bond-burn candidate; band median unaffected |

## 4. Coverage floor

- impl/: every module has a test file; every Law cited in a docstring has at least one
  test exercising it (current: 61 tests; grow with the code).
- sim/: every summary metric in results/summary.json must trace to a line in this file.
- No new protocol code merges without a test that fails without it.
