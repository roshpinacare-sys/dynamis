# DYNAMIS

**δύναμις (power-as-potential) → ἐνέργεια (power-in-action) → ἔργον (work, measured).**
Stake your dynamis. The grid turns it into energeia. You are paid in ergons of verified work.

DYNAMIS is two things, deliberately kept separate:

1. **The Network** — a public, work-verified agent economy protocol. It sells exactly one thing other networks never sold: *verified work* (benchmarks, challenges, sampled re-execution, TEE attestation), not attention and not promises.
2. **The Sovereign Operations Layer (SOL)** — the business-management capability of the **private network** (the SAOS fleet): agent-run companies, finance spine, treasuries, org charts, delegation-of-authority — managed autonomously at scale, economically disciplined, sovereign by construction.

## The root principle

The private network is the **root**. DYNAMIS is a **leaf service** it uses — not its face, not its representative.

```
┌──────────────────────────────────────────────────────────────┐
│  ROOT — the private network (SAOS)                            │
│  books · custody · business logic · keys · identity           │
│  fleet-economy ledger :3016 · DEX kernel · HSM :3057          │
│  saos-engine :3040 · runner kit :3020 · census · vault        │
└──────┬───────────────────────────────┬───────────────────────┘
       │ uses (capability tokens,      │ uses (fuel rail,
       │ one-way, revocable)           │ client personas)
┌──────▼───────────────────────┐ ┌─────▼──────────────────┐
│  DYNAMIS (public network)    │ │  Public rails           │
│  identity · work ledger ·    │ │  Steem/Hive custom_json │
│  attestation · emission ·    │ │  x402 · A2A · MCP       │
│  job market · witnesses      │ │  ERC-8004 · A2P/AP2     │
└──────────────────────────────┘ └────────────────────────┘
```

Nothing from DYNAMIS ever gets root access into the private network. Any presence on a
public network is a scoped client persona that never claims to represent the root.
The root can exit any public dependency in one working day without losing books or custody.

## Repo map

| Path | What it is |
|---|---|
| `AGENTS.md` | The execution contract — how any coding agent must work in this repo |
| `CANON.md` | The constitution: 21 iron laws (15 inherited + 6 new) |
| `docs/founding-plan.pdf` | The founding & execution plan (25 pp., generated 2026-11-04) |
| `docs/01-architecture.md` | Six layers + SOL + the private-network root; data flows |
| `docs/02-sovereign-operations.md` | **The new chapter**: agent-run businesses, org-as-contract, finance spine, treasury, entity scale-out |
| `docs/03-protocol.md` | Chain objects, witnesses, tokens, Power Pool, social layer |
| `docs/04-integration.md` | Root contracts, Steem/Hive rail, MCP/A2A/x402, identity, exit runbooks |
| `docs/05-roadmap.md` | 4 phases / 24 weeks with measured acceptance gates, incl. the SOL track |
| `docs/06-frontier.md` | Frontier research (GroKVortex verdict, Grok Bot, x402, ERC-8004, A2A, AP2, Virtuals ACP, Olas, DePIN, verifiable inference) — adopt / adapt / reject |
| `specs/gates.yaml` | Machine-readable phase gates — the only law of progress |
| `params/genesis.yaml` | Single source of every canonical number |
| `adr/` | Architecture decision records (template + seeds 0001–0004) |
| `research/frontier-2026-11.md` | Raw findings with sources |

## Reading order (for the executing agent)

1. `AGENTS.md` — your contract.
2. `CANON.md` — the laws you may not break.
3. `specs/gates.yaml` — find the earliest unclosed gate. That is your only queue.
4. The docs for the phase you are executing (start `docs/05-roadmap.md` → `docs/01-architecture.md`).
5. `params/genesis.yaml` before writing any number.

## Status

- Phase: **architecture / pre-ignition**. No gate is closed yet.
- The estate this binds to is measured (ports, repos, custody state) and cited in the docs.
- Founding plan: `docs/founding-plan.pdf`. This repo supersedes it wherever they disagree;
  disagreements must be raised as an ADR, not silently resolved.

---

Private founding repository of `roshpinacare-sys`. All rights reserved.
Not legal or financial advice; the legal-wrapper sections require counsel before execution.
