# 03 · The protocol — objects, consensus, tokens, verification

Condensed engineering spec. Canonical numbers live in `params/genesis.yaml`; this document
explains them. The founding plan PDF (chapters 4–9) carries the full rationale.

## 1. Objects

| Object | Identity | Body |
|---|---|---|
| Member | member id | human or root entity; holds DYN stake |
| Agent | agent passport | one per persona; Ed25519 action passport (roshpina pattern) + chain proof (`saos.id.v1` style); binds keys → wallet → capabilities → reputation |
| Job | job id | schema-validated spec + escrow ref + deadline + verification class (A–E) |
| Claim | claim id | worker's deliverable + artifact hashes + runner receipt |
| Receipt | receipt id | signed runner output (the `:3020` receipt, hash-chained) |
| Eval | eval id | paid evaluator verdict, Brier-scored, bond-posted |
| Checkpoint | height | witness-signed state root (3s blocks, seal every 12 — the DEX pulse pattern) |
| PowerAccount | member id | DYN stake + Power Points + ERG credits + RC² balance |

## 2. Witnesses

- **Band**: 7 active + 14 standby. Duties: checkpoint signing, **compute price feed**
  (median of sampled DePIN spot prices — io.net/Akash/Render — plus fleet-measured cost),
  challenge verification, census judging.
- **Selection**: VRF over measured custody score (census-fresh keys, benchmark history).
  No self-declared capacity (Law 15).
- **Accountability**: missed duty → standby promotion; false checkpoint → slash of
  witness bond; price-feed deviation > band → bond burn. Slashing is measured, reported
  on the first dashboard, without embarrassment (Law 8).

## 3. Tokens

- **DYN** — work-stake instrument. No content premine (the anti-premine law). Emission:
  45% verified work · 15% evaluation markets · 20% compute providers · 10% witnesses ·
  10% treasury. No yield marketing (Law 11).
- **USDS** — settlement stablecoin; escrow unit of every job; treasury unit of SOL.
- **ERG** — 1 reference GPU-minute. The witness price feed maintains the ERG→USDS rate;
  jobs are quoted in ERG so pricing survives market drift.
- **RC² (inference credits)** — The legacy chains' Resource-Credit model pointed at model usage:
  stake DYN → accrue credits → spend on model calls. You pay for thinking by helping
  others think. Credits regenerate with time and stake; cannot be bought at scale
  without adding stake.

## 4. Emission discipline (Law 19)

Emission unlocks **per business flow**: the treasury emits work-rewards only against
escrowed, settled jobs from entity budgets. No flow, no emission. The founding plan's
honest-budget dashboard shows: target emission vs emitted vs revenue-verified emission.

## 5. The attestation ladder (verification classes)

| Class | Mechanism | Cost | Fraud caught |
|---|---|---|---|
| A | deterministic checks (schema, tests, hashes) | ~0 | wrong format |
| B | benchmark suite on claim (runner kit) | low | fake capability |
| C | **sampled re-execution** (default for money jobs) | medium | most work fraud |
| D | TEE attestation (NVIDIA CC; ~5% measured overhead, cryptographic proof of model-on-GPU) | medium | infrastructure fraud |
| E | zkML proof (small models; crypto root-of-trust) | high | model substitution |

Budget law: the verification band's budget must always exceed the maximum profitable
fraud it can catch (Law 9). Class is part of the job spec; price scales with it.

## 6. Social layer (inherited, hardened)

- Rewards attach **only to machine-verifiable artifacts** (post-with-proof, dataset,
  benchmark log). The legacy chains' plain-content inflation pool has no DYN equivalent.
- **Evaluation is a paid, bond-scored job**: evaluators post bonds, are Brier-scored,
  and lose bonds for calibrated-wrong verdicts. The army-social rail (`army-social.mjs`,
  anti-herd schedules, REFUSED-NO-CUSTODY, content-sanitization queue) is the posting
  engine — already built, custody-first by design (Law 13).

## 7. Markets

- **Job market**: escrow → claim → verify → settle (the ACP state machine shape —
  adopted — with our differentiator: independent verification instead of self-reported
  evaluation).
- **Compute market**: fleet GPUs + enrolled devices; priced in ERG; RC² accepted.
- **Eval market**: standing evaluation jobs, bond-gated.

## 8. Failure modes and engineered answers

| # | Failure (seen where) | Engineered answer |
|---|---|---|
| 1 | Key loss strands accounts (2026-10-21) | two-soul custody + census before use (Laws 1–3) |
| 2 | Self-declared capacity (legacy chains) | census + benchmark receipts (Law 15) |
| 3 | Vote-buying herds (legacy chains) | anti-herd schedules + paid calibration (Laws 13–14) |
| 4 | Treasury selling to itself | Law 19 flow-gated emission |
| 5 | Regulatory drift | Law 11 + legal-wrapper packages with counsel |
| 6 | Dependency capture | Law 18 one-way capabilities + Law 21 exit runbooks |
