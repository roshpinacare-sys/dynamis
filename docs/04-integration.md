# 04 · Integration — how the root uses networks without becoming them

## 1. Root contracts (what DYNAMIS may consume)

The root kernel exposes five contract surfaces to DYNAMIS, each behind a capability
token (scoped, time-boxed, revocable — Law 18). DYNAMIS never receives: root keys,
ledger write access to entity books, or business logic.

| Contract | Source (exists) | Used for |
|---|---|---|
| Ledger API | `fleet-economy@:3016` (append-only, `/verify` whole-chain) | settlement finality, treasury ops |
| Runner API | `sovereign-runner-kit@:3020` + `netrun.sh` (`status|claim|verify|done`) | job execution, receipts |
| Custody API | HSM `:3057` (`/sign {keyRef,digestHex}`, fail-closed) + census | all value-signing, roster of the living |
| Identity API | `saos-id-verify` (`saos.id.v1` custom_json proof), roshpina passports | agent passports, cross-chain proof |
| Anchor API | `saos-jummper` (~$0.10 batched notary), `TruthRail` (zero-gas) | Merkle anchoring of digests |

**One-way rule**: DYNAMIS events may notify the root; nothing may *write* into root
state except through the Ledger API with a capability minted per-entity.

## 2. The estate fuel rail (sits on it, never represents it)

- Live today: DEX relay via `custom_json` on both chains; the army rail posts/votes
  under persona accounts (`headcorner`, `woq`, `lsa`, `siq` + funded soldiers).
- Rule (Law 17): these personas are clients. Their bios never claim to represent the
  root or any entity. Their keys pass the census like every other key; the 2026-10-21
  lesson is permanent.
- Purpose: fuel (visibility, SP curation for the treasury arteries), experimentation,
  and a live testbed for the anti-herd social engine.

## 3. External protocol stack (adopt / adapt)

| Protocol | Decision | Where it plugs |
|---|---|---|
| **x402** (HTTP-402 stablecoin payments; 100M+ agentic payments on Base per Chainalysis, 2026-06) | **Adopt** | jobs API and RC² gateway accept x402 for external machine clients; SOL invoicing speaks x402 for machine-native B2B |
| **MCP** (already in estate: `mcp.mjs` stdio server) | **Adopt (extend)** | add `saos_jobs_*` tools behind capabilities; the fleet's MCP pattern (regex-scrubbed output) is the security baseline |
| **A2A** (Linux Foundation, 150+ orgs, enterprise production 2026) | **Adopt** | publish A2A agent cards for DYNAMIS personas; accept A2A for agent-to-agent job negotiation |
| **ERC-8004** (trustless-agent registries: identity, reputation, validation) | **Adapt (bridge)** | keep DYNAMIS registry authoritative on its own chain; export mirror records to an ERC-8004 registry for external discovery |
| **AP2 / Visa TAP / Mastercard Agent Pay** | **Track → adopt consent patterns** | SOL procurement mandates and human-approval artifacts follow AP2's mandate/consent shapes when serving regulated clients |
| **L402** | **Adapt** | metered streaming APIs where x402 per-call is too chatty |
| **Virtuals ACP** | **Adapt state machine** | escrow→deliver→evaluate→settle shape; differentiator = independent verification (attestation ladder), not self-report |

## 4. Agent identity — one directory, many proofs

The estate audit found identity fragmented across Ed25519 passports, secp256k1 chain
proofs, GitHub PATs, and engine-held WIFs. SOL unifies:

```
Agent Directory (root service, new)
  agent_id → {passports[], chain_proofs[], keyrefs[](HSM), capabilities[], wallet[](PowerAccount), reputation[]}
```

- Passports: Ed25519 action passports (roshpina) for local action signing.
- Chain proofs: `saos.id.v1`-style custom_json for cross-network personas.
- Keys: **never in the directory** — only HSM keyrefs (Law 3).
- Reputation: attestation-ladder grades + evaluation Brier scores.
- ERC-8004 bridge: export a mirror so external ecosystems can discover agents without
  the root depending on them (Law 21).

## 5. Exit runbooks (Law 21 — written on day one of each integration)

Each integration file in `specs/` carries an `exit:` block. Standard form:

```yaml
exit:
  trigger: ["circuit breaker open > 24h", "counsel flag", "owner veto"]
  steps: ["freeze rail persona keys", "drain escrow to treasury", "disable capability", "archive digests to root books"]
  budget: "≤ 1 working day"
  loss_check: "books and custody unaffected"
```

If an integration cannot pass this form, it is not built (Law 21 is a design gate, not
an afterthought).
