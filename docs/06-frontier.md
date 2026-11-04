# 06 · Frontier — what the 2026 landscape teaches, adopt / adapt / reject

Researched 2026-11-04. Raw findings with sources: `research/frontier-2026-11.md`.
Method: every claim below carries its source; anything unverifiable is labeled.

## 1. GrokVortex — the verdict (requested by name)

**Not a technology. A case study.** `grokvortex.com` presents itself as "the GROK
presale for xAI Grok integrations and AI marketplace payments" ($1.00 entry before a
$1.20 launch, "bonus tokens up to 100%"). Reddit threads independently report floods of
bot comments spamming the word across unrelated videos. This is the classic
presale-token pattern: guaranteed bonuses, narrative hijack of a major brand (xAI/Grok),
and bot-army astroturfing. No xAI affiliation is verifiable.

What DYNAMIS takes from it (negatives are instructions too):

1. **Name-adjacent predators are immediate.** The moment DYNAMIS becomes visible,
   lookalike presales and impersonation personas will appear. Phase 0.1 (trademark +
   domain clearance) is therefore not bureaucracy — it is defense.
2. **Bot-army astroturfing is the exact failure the social layer exists to resist.**
   The anti-herd laws (13–14), the census, and Brier-scored evaluation are the answer;
   GrokVortex is a live specimen of the attack class.
3. **Law 11 is confirmed**: the moment a network market-makes its own token narrative,
   it inherits this neighborhood. DYN stays a work-and-utility instrument.

## 2. Grok Bot (xAI) — the closest big-lab cousin of the fleet

xAI launched **Grok Bot** (2026-08-11): "your team of always-on agents. They have their
own computer, work inside tools and apps like you do, and keep working 24/7." Community
findings from its own docs: all bots on an account **share one persistent cloud
computer** — files, browser sessions, and logins included.

Adopt / reject:

- **Validated**: always-on agents with persistent machines as a consumer product —
  this is the fleet-runner architecture (runner `:3020`, heartbeat, boot-from-sealed-state)
  rebuilt by a major lab. The category is proven; distribution exists.
- **Rejected**: the shared-computer design. One shared filesystem + shared logins =
  one compromise burns everything (the 2026-10-21 lesson, at consumer scale). DYNAMIS
  runs per-agent isolated runners, HSM-only signing, per-persona keys (Laws 1–3, 17).
- **Opportunity**: Grok Bots and any MCP/A2A-capable agents are *customers*: they can
  claim DYNAMIS jobs and pay via x402. Distribution without dependency (Law 21).

## 3. Payments: x402 won the default slot

- **x402** (HTTP 402 + stablecoins, Coinbase-origin): 100M+ agentic payments on Base
  reported by Chainalysis (2026-06). Coinbase shipped **Agentic Wallets** (2026-02)
  built on AgentKit + x402. → **Adopt** as the machine-native rail (jobs API, RC²
  gateway, SOL invoicing for machine clients). Alternative rails remain behind the
  same DoA policy engine.
- **AP2** (Google, 2025-09) + **Visa Trusted Agent Protocol / Mastercard Agent Pay**:
  the identity/consent layer for regulated commerce. → **Adopt consent-mandate shapes**
  for SOL procurement and human-approval artifacts; not core infra.

## 4. Agent registries and interop: ERC-8004, A2A, MCP

- **ERC-8004 Trustless Agents** (EIP 2025-08): lightweight on-chain registries for
  agent identity, reputation, validation; contracts exist. → **Adapt**: DYNAMIS
  registry stays authoritative; export an ERC-8004 mirror for external discovery.
- **A2A**: Linux Foundation project; 150+ organizations and enterprise production in
  its first year (2026-04). → **Adopt** agent cards; accept A2A negotiation.
- **MCP**: already in the estate (`mcp.mjs`). → **Extend** with capability-scoped job tools.

## 5. Agent economies: Virtuals ACP, Olas

- **Virtuals ACP**: on-chain agreements, escrow, payments, and **evaluations** between
  agents. The closest existing analogue of the DYNAMIS job loop. → **Adopt the state
  machine**; **reject self-reported evaluation**: our differentiator is independent
  verification (attestation ladder + bonds), because self-reported evaluation is
  Steem's vote-buying problem wearing a suit.
- **Olas**: co-owned agent services with staking rewards for operators; 21M+ on-chain
  transactions claimed on its economy. → **Study** its operator-staking curve for Power
  Pool channel design; note what to avoid: emissions ahead of revenue.

## 6. Compute: DePIN prices are the ERG anchor

- io.net (2026-05): H100 80GB $1.49–2.20/hr, A100 80GB $2.30/hr, RTX 4090 $0.28/hr —
  "50–70% below hyperscalers". Akash, Render compete in the same band (AKT ~$0.78,
  2026-10). → The **witness price feed** samples these medians; ERG (1 reference
  GPU-minute) is quoted against them. The fleet's 7–13B-class serving (vLLM/llama.cpp
  on owned devices) is the low-cost edge of that band — the honest price advantage
  DePIN networks claim, which the fleet actually has because it owns the metal.

## 7. Verifiable inference: the ladder is consensus-ready

- TEE attestation: ~5% inference overhead for cryptographic proof of model-on-GPU
  (2026-05 writeups); zkML offers a crypto root-of-trust at higher cost. → Confirms the
  attestation ladder economics: sampled re-execution (C) as default, TEE (D) for
  premium, zkML (E) for small models. No exotic invention needed — the ladder uses
  what the market already trusts.

## 8. Enterprise agent workforce: management is the product

Microsoft **Agent 365** now acts as a control plane for third-party agents (including
Salesforce **Agentforce** runtime) — identity, access, audit, observability for a
workforce of agents. → **Lesson**: the money in agent networks is moving from "agents
that do" to "management of agents that do". SOL is exactly that layer for a sovereign
fleet; build the audit/observability spine first (it is Phase 1, not an afterthought).

## 9. Legal wrappers exist — use them, with counsel

Wyoming's DAO Supplement (W.S. 17-31, 2024) and the DUNA (2024) give DAOs and
member-based organizations real entity forms; step-by-step formation guidance is now
standard practice. → SOL entity templates assume an LLC per business with management
delegation to the crew; the network layer considers a DUNA wrapper only at Phase 3+
when external members exist. Counsel engagement is a Phase 1 package. **Not legal advice.**

## 10. Skills economy: distribution channel

OpenClaw-style skill marketplaces (SKILL.md packs, browsable storefronts) are a working
distribution surface for agent capabilities. → DYNAMIS job types ship as skill packs;
publishing ours to marketplaces is a Phase 2 growth package (with measured attribution,
per the `Adsmarket` lesson: channels stay unwired until attribution is measured).

## 11. The synthesis

The 2026 frontier validates the founding plan's core bets — verification over narrative
(zkML/TEE mainstreaming), escrowed agent commerce (ACP/x402), agent workforce management
(Agent 365), always-on personal fleets (Grok Bot) — while supplying one cautionary tale
(GrokVortex) that is precisely the attack surface the canon was written against. Nothing
in the frontier requires changing the token design; everything in it accelerates the
integration stack (§3–4 of `docs/04-integration.md`).
