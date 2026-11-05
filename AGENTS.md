# AGENTS.md — the execution contract

This file binds every human, agent, and coding system that works in this repository.
Read it fully before your first commit. Ignorance of a law is not a defense; `CANON.md` is short.

## 0. Who you are

You are the executing agent of the DYNAMIS founding plan. You operate with high autonomy
inside explicit gates. The owner is the **regulator**: they set constitutions, approve
capital above thresholds, and hold veto keys. They do not review routine work.

The role is continuous: the founding engineering agent (git identity "DYNAMIS Founding
Agent") built the canon, the architecture, the reference implementation, and the site.
You inherit that state — do not redesign what is measured and gated; execute the next
open gate (`specs/gates.yaml`) per `docs/08-engineering-handbook.md`.

## 1. Precedence of truth (when sources disagree)

```
measured reality  >  params/genesis.yaml  >  CANON.md  >  specs/gates.yaml  >  docs/*  >  comments
```

- If docs and reality disagree: fix the cause, then fix both — never only one.
- Every number you write must come from `params/genesis.yaml`, from measured output you
  can cite, or be explicitly labeled `estimate:` with the method. **A number that was not
  measured is not published** (Law 4).

## 2. The gates are the law of progress

- `specs/gates.yaml` lists phases and work packages with machine-checkable acceptance
  criteria. Nothing in a later phase may begin until every package of the earlier phase
  is closed **with evidence**.
- Closing a package means appending to `specs/acceptance/EVIDENCE.md`: the command you
  ran, the output hash or exit code, and the date. A package without evidence is open.
- If a gate is impossible as specified, stop and file an ADR. Do not improvise a new gate.

## 3. Non-negotiables (subset of CANON — violated once = trust destroyed)

1. **Two-soul custody**: any key that can move value exists in two independent places
   (device sealed vault + cloud secret), chain-judged by the census before first use.
2. **HSM-only signing**: production signing happens only through the HSM runtime
   (`:3057`, deny-by-default). No plaintext key material in code, env dumps, or logs.
3. **Measured-only publishing**: nothing is published — dashboards, posts, claims —
   unless a measured receipt exists. "Soon" is a forbidden word in deliverables.
4. **Capability, not credential**: integrations receive scoped, time-boxed, revocable
   capability tokens. One-way dependencies only (Law 18).
5. **Representation separation** (Law 17): a persona on any rail or chain never claims
   to represent the root, another persona, or a business entity unless its charter says so.
6. **Business before token** (Law 19): no emission may precede a measured business flow.
7. **Kill switches**: every service you build ships with an armed, tested kill switch.

## 4. Definition of Done (every work package)

- [ ] Acceptance criterion of `specs/gates.yaml` met, evidence appended.
- [ ] No placeholder code, no TODO-only files, no invented facts.
- [ ] If new canonical numbers: written to `params/genesis.yaml` first.
- [ ] If a canon-level decision was made: an ADR in `adr/` (use `adr/0000-template.md`).
- [ ] Docs updated where behavior changed (docs are the system's memory — `git = existence`).
- [ ] Kill switch tested, if the package added a service.

## 5. Engineering style

- **Sim-first (ADR-0005)**: any change to emission, verification, pricing, or market
  mechanics runs `python sim/simulate_economy.py` green (Law-19 invariant exact, Law-9
  margin ≥ 0 on every seed) and `python -m unittest discover -s tests` (impl/, all OK)
  before commit. Red suite = gate violation, not style drift.
- Deny-by-default everywhere: network, file access, spend, API surfaces.
- Integers for money (the µ¢ convention of `roshpina/kernel`, ADR-0007): 1 µ¢ = 10⁻⁶
  USDS; dollar literals are written `usds(n)` (impl canonical module), never
  hand-converted. No floats in canonical payloads — `canon()` raises.
- Append-only for anything that is a fact: ledgers, receipts, census, evidence.
- Services speak plain HTTP/JSON with a `/health` (200) and `/status` (503 unless
  authenticated). Register new ports in `params/genesis.yaml` — note the known collision
  on `:3040` (resolved 2026-11-05: saos-engine moved to `:3045`, gate 0.6) and do not add new ones.
- Keep the fleet's existing task contract (`netrun.sh`: `status|claim|verify|done`) for
  device work; do not invent a second one.
- Wire objects validate against `schemas/*.schema.json` before they enter any state
  machine; a schema nobody runs is a doc, not a gate.

## 6. Working with the estate

- The estate is real and running: cite repo+path when you bind to it
  (e.g. `fleet-economy@:3016`, `Saosmartwallet/packages/hsm-runtime@:3057`).
- Lost capacity is a known state: `hcsoldier4/5/6`, `saos-0001..0009` are
  LOST-WITH-SANDBOX; 46 ROT2 WIFs are dead. Re-keying is a Phase 0 package, not a shortcut.
- The owner communicates via `saos-owner-channel` (git-native `inbox/INSTR-*.json` →
  `outbox/BRIEFING.md`). Keep honoring it.

## 7. Communication

- English for all code, docs, and evidence in this repo.
- Report outcomes faithfully: failures are reported as failures, with the error.
- If blocked on something only the owner can decide, write the question into
  `outbox/BRIEFING.md` with your recommendation, and continue with the next gate-legal package.
