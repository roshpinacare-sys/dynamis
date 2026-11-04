# 02 · The Sovereign Operations Layer — agent-run businesses at scale

This is the chapter the founding plan pointed at but did not yet write: how the private
network **manages businesses and organizations — wide-scale, autonomous, sovereign — and
economically sound**. The estate audit (2026-11-04) is blunt: the fleet has a real
ledger, escrow, passports, receipts, and a work contract — but **no invoicing, no CRM,
no contracts, no payroll-as-a-process, no budgeting**. The mandate on file even says
"internal users only". SOL is the deliberate construction of the missing half, without
breaking the internal-only mandate: entities are *root constructs*, external clients are
served through personas and rails, never by exposing the root.

## 1. Org-as-Contract (Law 20)

An entity is a canon object, not a chat. Minimum schema (canonical copy lives in
`params/genesis.yaml#entities`):

```yaml
entity:
  id: ent-001                     # ulid
  kind: llc                       # llc | dao-llc | internal-office
  charter:                        # purpose, term, prohibited acts
    purpose: "B2B content & data-ops services"
    prohibited: ["custody of client keys", "yield marketing"]
  doa: doa-001.yaml               # delegation of authority matrix (below)
  budgets:                        # envelopes, per period, hard-capped
    ops:    {cap_usds: 3000, period: monthly}
    growth: {cap_usds: 1500, period: monthly}
  kpi_tree: kpi-001.yaml          # north-star → department KPIs → job specs
  regulator: owner-via-scribe     # the named human veto holder
  crew: [chief-of-staff, finance, ops, growth, legal, support, intelligence]
  ledger: ent-001.jsonl           # own append-only book at the root
  keys: {signing: hsm-keyref-rotating, rail: persona-scoped}
```

**Delegation of Authority matrix** — the spine of autonomous-but-bounded operation:

| Class | Example | Agent authority | Human quorum |
|---|---|---|---|
| T0 routine | pay a $40 API bill from ops envelope | auto | none |
| T1 committed | sign a $500/month vendor contract | auto (≤ budget) | notify |
| T2 capital | spend > $2,000, any hire with pay | prepare + recommend | 1 human yes |
| T3 constitutional | DoA change, charter change, new entity | draft only | regulator veto keys |
| X forbidden | client key custody, yield promises, unmeasured claims | never | never |

The policy engine that enforces DoA is a **kernel extension, not a new service**: the
`fleet-economy` writer (append-only, double-balance) gains a policy hook — deny-by-default,
fail-closed, exactly like the existing G28 routing policy, which is the precedent.

## 2. The crew — departments as bounded agents

Departments are *roles bound to job-market subscriptions*, staffed by fleet agents with
capability tokens — none holds keys above its DoA class:

- **Chief-of-staff** (exists: `saos-sovereign-foundry` organs, FleetHQ Decision Podium):
  decomposes charter → weekly work orders → jobs.
- **Finance** (builds on `fleet-economy`, `roshpina/kernel`, Autonomy `artery-treasury*`):
  AP/AR, invoicing, payroll streams, tax calendar, finance digest.
- **Ops**: procurement, vendor scorecards, SLA tracking; executes through `netrun`.
- **Growth**: pricing, funnels, the `Adsmarket` campaign kits (currently unwired — SOL
  wires them behind a measured-attribution gate).
- **Legal-compliance**: contract templates, renewal radar, KYB files, regulator filings.
- **Support**: inbound tickets become escrowed jobs; SLA breach = auto-credit.
- **Intelligence**: market monitor; feeds the pricing agent and the witness price feed.

Hiring is a market operation: a role is a standing job spec; agents qualify by their
attestation ladder grade (see `docs/03-protocol.md` §5), not by self-description.

## 3. The finance spine

Everything runs on the existing double-entry primitives — **no second accounting database
(ADR-0004)**:

1. **Chart of accounts** mapped onto the µ¢ BigInt ledger (`roshpina/kernel` convention:
   integers only, no floats — ever).
2. **Accrual events**: invoice issued / received, revenue recognized, depreciation —
   as ledger event kinds appended to the entity's own `*.jsonl` book.
3. **Invoicing out**: quote → invoice → collect. E-invoice formats (UBL/FACT2-style XML)
   rendered from ledger events; collection via x402 (machine clients), stablecoin rails,
   or bank rails (human clients) — each a persona-scoped capability, never a root key.
4. **Invoicing in**: vendor bills parsed → DoA check (class T0–T2) → scheduled payment.
5. **Payroll as a process**: worker registry (agent → role → rate → schedule → payout
   stream). Streaming payouts on USDS (Superfluid-style per-second accrual) settle the
   existing salary transaction kind; tax/compliance hooks are template stubs until
   jurisdiction facts exist (marked, not invented).
6. **Audit**: every entity book is hash-linked (the fleet-economy pattern) and Merkle-
   anchored via the ~$0.10 batch notary. The anchor proves the books existed; the books
   themselves never leave the root (Law 16).

## 4. Treasury and risk (the economic discipline)

- **Reserve policy** is canon: `min_runway_months` (default 6) is a genesis parameter;
  any spend that breaches it is T2 regardless of amount.
- **Capital allocation committee**: agents prepare decisions (with unit-economics math);
  the regulator approves above threshold; cadence weekly (a standing job, minuted to the
  entity book).
- **Counterparty limits & fraud quorum**: per-rail caps (pattern: G28's maxFlow/daily-cap,
  fail-closed); anomalous outflows freeze the rail and page the regulator.
- **Rails matrix**: x402 for machine-native per-call commerce; L402-style metered for
  streaming APIs; stablecoin transfer for B2B; bank rails for the fiat edge. Every rail
  has an exit runbook (Law 21).
- **Insurance posture**: start self-insured from reserves; parametric covers evaluated
  when measured claim history exists — not before.

## 5. Entity scale-out — "businesses at wide scale"

Spinning a new business is a **template instantiation**, not a project:

```
instantiate(ent-N) := charter(seed) + doa(template) + budgets(alloc) + crew(subscriptions)
                    + ledger(new book) + keys(census-fresh, two-soul) + day-one checklist job
```

- Isolation is total: per-entity ledgers, keys, envelopes, risk caps. Consolidation is a
  read-only view for the regulator console (`giant@:3000` is the pattern).
- The first entity (Phase 0–1) is the network's **own operating entity** — it pays the
  fleet's real costs and issues the fleet's first real invoices, satisfying Law 19 before
  any emission.
- Target shape (target, not promise — Law 8): 3 entities by Phase 3, each with a measured
  P&L, sharing one crew pool and one treasury policy engine.

## 6. The human as regulator

The owner approves: constitutions, DoA changes, T2+ spend, legal facts, and key ceremonies.
The owner never does: routine ops, daily trading, posting, bookkeeping. The existing
`saos-owner-channel` git protocol (inbox `INSTR-*.json` → outbox `BRIEFING.md`) is the
regulator interface; veto keys are separate from every operational key.

## 7. Legal wrapper strategy (requires counsel — not legal advice)

- Per-business entity: an LLC (Wyoming or comparable) whose operating agreement delegates
  management to the agent crew within the DoA, with a human member/signatory of record
  for banking.
- Network layer: a DUNA/DAO-LLC wrapper becomes relevant only when external members
  exist (Phase 3+); Wyoming's DAO Supplement (W.S. 17-31) and DUNA (2024) are the
  studied templates; counsel engagement is a Phase 1 work package.
- What is never delegated: custody of client funds beyond escrow, and anything class X.

## 8. Why entities close the loop

Entities are the **demand side** of DYNAMIS. The Power Pool accumulates supply (agents,
stake, compute); entities buy verified work from real budgets; emission follows that
revenue (Law 19). A network whose largest customer is its own treasury is a node selling
to itself — the Steem failure mode. A network whose customers are managed businesses with
measured P&Ls is an economy.
