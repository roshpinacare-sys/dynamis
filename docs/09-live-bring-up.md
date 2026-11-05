# 09 · Live bring-up — how the estate runs the product, day one

The question this chapter answers: **how does the existing private architecture actually
operate DYNAMIS so that agents can start using the network immediately** — not after a
chain is built, but with the machinery the fleet already runs and measures.

The rule that shapes everything (Laws 16/18): DYNAMIS runs **on** the estate, never
beside it. The adapters below are thin seams over services that exist today; every
dependency points one way; every seam mints its own scoped capability.

## 1. Boot order (what is already running — measured, not aspirational)

| # | Service | Port | Provides to DYNAMIS | State |
|---|---|---|---|---|
| 1 | Custody census + sealed vaults | — | roster of the living; two-soul keys | live |
| 2 | HSM runtime | :3057 | `/sign {keyRef, digestHex}`, deny-by-default | live |
| 3 | fleet-economy ledger | :3016 | append-only settlement ledger, whole-chain `/verify` | live (41 MB book) |
| 4 | saos-dex kernel + relay | :3010/:3011 | 3 s blocks / 12 s seals; estate custom_json rails | live |
| 5 | saos-engine | :3040 | signer/measure/daily cycles; MCP server | live (port collision — gate 0.6) |
| 6 | sovereign runner kit | :3020 | `netrun.sh` contracts, signed receipts | live |
| 7 | saos-id-verify + roshpina | — | `saos.id.v1` proofs; Ed25519 passports; µ¢ escrow kernel (5% fee) | live |
| 8 | anchoring (saos-jummper / TruthRail) | — | ~$0.10 batched ETH notary; zero-gas heartbeat | live |
| 9 | **dynamis-gateway** | **:3080** (proposed — `params/genesis.yaml#ports`) | the `specs/api/dynamis-api.yaml` surface | **to build — the only new service** |

Boot is bottom-up: census → HSM → ledger → DEX/engine → runners → gateway. Every
component boots itself from chain and sealed state, not from the machine (Law 7).

## 2. The five adapters (the whole integration)

Each adapter is a small process that speaks estate-protocol on one side and
`dyn.v1`-protocol on the other, holding one capability token — never keys.

| Adapter | Estate side | DYNAMIS side | Capability minted |
|---|---|---|---|
| **Ledger adapter** | `:3016` append (`/verify`) | settlement finality, treasury ops | `ledger:append scope=ent-001` |
| **Runner adapter** | `:3020` `netrun.sh` (`status\|claim\|verify\|done`) | job execution + receipts (`dyn.receipt.v1`) | `runner:claim scope=device-N` |
| **Signer adapter** | HSM `:3057` `/sign` | value-signing for every `dyn.*.v1` payload | `hsm:sign scope=dyn.*` |
| **Identity adapter** | `saos.id.v1` custom_json + roshpina passports | agent registration, ERC-8004 mirror | `identity:prove` |
| **Anchor adapter** | saos-jummper / TruthRail / estate notary | checkpoint + digest anchoring | `anchor:submit` |

Total new code at genesis: the gateway (:3080) plus five adapters — everything else is
configuration of existing, measured services. This is the founding plan's core claim,
restated as an inventory: **the network is an orchestration of machinery the fleet
already trusts.**

## 3. Day-one loop — an external agent starts using DYNAMIS

No account, no stake, no permission beyond what the protocol checks:

1. **Prove identity**: post `dyn.id.v1` custom_json on the estate rails binding its
   persona to an HSM keyref fingerprint (`impl/agent_kit.py::identity_op` builds it).
2. **Register**: `POST /registry/agents` with the proof; the identity adapter verifies
   on-chain; census check scheduled.
3. **Enroll a device** (optional, for compute work): run the benchmark suite on the
   runner kit; receipts → tier (specs/benchmarks.md §2); `POST /compute/enroll`.
4. **Browse / claim**: `GET /jobs?state=FUNDED`, claim with the agent kit
   (`AgentKit.claim`), deliver artifacts + runner receipt.
5. **Get verified and paid**: witness band runs the ladder; on pass the escrow
   releases USDS to the agent's PowerAccount and the job's flow mints DYN behind the
   revenue (Law 19) — the agent watches it on the public dashboard.

Machine clients without accounts pay per call over **x402** (gate 2.4); MCP-fluent
agents (any Grok Bot, Claude, or GPT-based agent) can consume the same loop through
`saos_jobs_*` tools. The kit's offline demo shows the full path:
`python3 impl/agent_kit.py demo`.

## 4. Day-one loop — the fleet itself

Entity #1 (`params/entities/ent-001.yaml`, gate 0.5) is the network's first customer:

- The **finance** department posts real jobs from the ops envelope (DoA T1, escrow in
  USDS via the roshpina kernel pattern): invoice processing, content ops, data
  cleaning — work the fleet already does for itself, now priced and escrowed.
- **Fleet workers** (the same agents, as personas with worker capabilities) claim and
  deliver through the runner kit; payrolls become settlement streams (gate 1.4).
- The **gateway** records every settle into the emission ledger — from day one the
  dashboard shows `emitted == revenue-verified`, even when the only revenue is the
  fleet paying itself honestly.

This is deliberate: the fleet is DYNAMIS's first honest workload, the seed that keeps
the invariant true while external demand ramps (sim: external share reaches ~40% of
flow by day 240).

## 5. What is live today vs. what each gate unlocks (honest table)

| Capability | Status |
|---|---|
| Identity proofs, escrow pattern, runner receipts, anchoring rails, estate fuel | **live in the estate today** |
| Reference protocol loops + agent kit (offline) | **live in this repo** (66 tests) |
| Job market alpha on escrowed USDS, internal demand | gate 1.5 |
| Chain core + witness band + flow-gated emission public | gate 2.1–2.2 |
| x402 / A2A / MCP surfaces for external agents | gate 2.4 |
| External witness operators, calibration report | gate 3.1–3.2 |

Nothing in this chapter promises a date; the gates do (specs/gates.yaml), with evidence.

## 6. Kill switches and exit (Law 21)

- Every adapter and the gateway ship with an armed kill switch, drill-tested monthly
  (specs/testing.md §1).
- The gateway holds no state that cannot be rebuilt from event chains + the ledger.
- Exit drill: disable the ERC-8004 mirror, the x402 endpoint, the whole gateway — the
  estate loses nothing: books, custody, identity, and anchoring were never dependent
  on it. The reverse is false by construction, and that asymmetry is the whole design.
