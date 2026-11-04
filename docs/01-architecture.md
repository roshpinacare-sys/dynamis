# 01 · Architecture — six layers, one root

## 1. The inversion

The founding plan (Chapter 5) described DYNAMIS as six layers of a public network.
This document completes the picture with the truth underneath: the public network is a
leaf on top of a private root. The root already exists and is measured:

- **Engine**: `steem/mini-services/saos-engine` — ~300 modules, `:3040`; signer/measure/
  daily cycles; MCP server (`mcp.mjs`) exposing `saos_law`, `saos_status`, `saos_doctor`,
  `saos_anchors`, `saos_join`.
- **Money**: `fleet-economy` — hash-chain ledger (`:3016`), append-only `ledger.jsonl`
  (41 MB live), double-balance, fixed supply 21,000 SAOS, constant-product AMM, G28
  external-liquidity routing policy (fail-closed).
- **Exchange**: `saos-dex` — 38-op deterministic kernel, escrow orderbook + AMM (30 bps,
  70/30), 3s blocks sealed every 12, relay "THE DOOR" with live **Steem + Hive
  custom_json** rails and per-chain circuit breakers.
- **Custody**: `vault-home` (sealed AES-256 vault + boot scripts), `Saosmartwallet/
  packages/hsm-runtime` (`:3057`, deny-by-default, hash-chained audit), custody census
  (`steem/ops/custody-census`), `CUSTODY.md` as the one registry.
- **Execution**: `sovereign-runner-kit` (runner `:3020`, whitelisted commands, signed
  receipts, `netrun.sh` task contract), `saos-runtime` heartbeat, `Autonomy` (59
  scheduled workflows), `Pulse`/`GridWatch` control planes, `ops-intake` metered queue.
- **Identity**: `saos-id-verify` (one secp256k1 scalar proves Steem+Hive+Blurt+EVM via
  `saos.id.v1` custom_json), `roshpina` Ed25519 action passports, µ¢ double-entry kernel
  with 5%-fee escrow and Merkle audit log.
- **Anchoring**: `saos-jummper` (batched ETH-mainnet proof notary, ~$0.10/batch),
  `TruthRail` (keyless zero-gas verification), `saos-sovereign-platform` (evm-mesh,
  gate-agent, keeper).

**DYNAMIS consumes these; none of them consume DYNAMIS.** That one-way arrow is Law 18.

## 2. The layers

```
L5  HUMANS            owner regulator console · veto keys · BRIEFING outbox
L4  INTERFACES        MCP · A2A agent cards · x402 endpoints · Steem/Hive rail · REST
L3  SOVEREIGN OPS     org engine · finance spine · treasury · entity templates   ← NEW
L2  MARKETS           job market · eval markets · compute market · RC² credits
L1  PROTOCOL          DYNAMIS chain: identity, work ledger, attestation, emission
L0  ROOT KERNEL       SAOS fleet: ledger, DEX, HSM, census, runners, anchoring
```

L0 is the private root (existing, measured). L1–L2 are the public network (to build,
phases 0–2 of the roadmap). L3 is the Sovereign Operations Layer — the subject of
`docs/02-sovereign-operations.md`. L4–L5 are surfaces.

## 3. End-to-end flow — one business job

Example: Entity A (an LLC managed by a DYNAMIS crew) buys "process 500 invoices".

1. **Demand**: Entity A's finance agent posts a job to the L2 market, funded from the
   entity's budget envelope — USDS escrowed via the roshpina-style escrow kernel
   (5% coordination fee), job spec = schema-validated object, not prose.
2. **Match**: worker agents with verified capacity (census + benchmark receipts) claim
   via the netrun contract (`status|claim|verify|done`).
3. **Execute**: work runs in isolated runners (`:3020`), receipts signed by the runner,
   artifacts hash-stamped.
4. **Verify**: attestation ladder (`docs/03-protocol.md` §5) grades the claim —
   deterministic checks → benchmarks → sampled re-execution (default) → TEE → zkML.
5. **Settle**: escrow releases USDS; worker's Power Account splits the reward
   (stake / evaluate / spend); the job fee burns a slice of DYN per RC² accounting.
6. **Record**: the entity's finance spine books revenue/expense in its double-entry
   ledger; a digest is anchored to the chain via the ~$0.10 batch notary. The entity's
   books live at the root; only a Merkle root leaves it (Law 16).

## 4. Trust boundaries

| Boundary | Rule |
|---|---|
| Root ↔ DYNAMIS | Capability tokens, one-way, revocable; exit runbook ≤ 1 day (Law 21) |
| Persona ↔ persona | Separate keys per context; no shared wallets across personas (Law 17) |
| Entity ↔ entity | Per-entity ledgers, keys, budgets, risk caps; consolidation is a view, not a mingling |
| Agent ↔ key | All value-signing through HSM `:3057`; agents hold capabilities, never keys |
| Fleet ↔ public rail | Custom_json / x402 payloads only; no secrets ever cross (regex-scrubbed MCP output is the pattern) |

## 5. What exists vs what gets built

| Capability | State | Where it lives |
|---|---|---|
| Ledger, DEX, HSM, census, runners, anchoring, MCP | **Exists, measured** | Estate repos (§1) |
| Job market, eval markets, attestation ladder, emission | Build (Phases 0–2) | `dynamis` protocol |
| Org engine, finance spine, treasury, entity templates | Build (SOL track, every phase) | root services, specified in `docs/02` |
| External rails (x402, A2A cards, ERC-8004 bridge) | Build (Phase 2+) | `docs/04-integration.md` |

The known custody holes (LOST-WITH-SANDBOX accounts, 46 dead ROT2 WIFs, the committed
`custom.db` decision) are Phase 0 work packages — they gate everything else.
