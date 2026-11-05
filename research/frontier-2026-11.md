# Frontier research — raw findings, 2026-11-04

All items were retrieved via web search on 2026-11-04 and are cited as found.
Anything not verifiable is explicitly marked.

## 1. GrokVortex (the name the owner asked about)

- `grokvortex.com` — "Grokvortex now available with biggest early bonus… the GROK
  presale for xAI Grok integrations and AI marketplace payments. Enter at $1.00 before
  the $1.20 launch, with bonus tokens up to 100%." (search snippet)
- Reddit r/youtube — "Suddenly seeing tons of bot comments with the word [grokvortex]…
  comments were unrelated to the subject." (search snippet)
- coinmooner.com listing for "grokvortex token" — "next-generation digital asset that
  combines AI innovation with blockchain technology… fair token distribution, real-world…" (boilerplate)
- Verdict: **presale token with classic red flags (guaranteed bonus, brand hijack,
  bot-comment spam). No verifiable xAI affiliation. Not integrated; treated as a case
  study of the astroturfing attack class.**
- Adjacent meme found: "Grok 4.20: the mystery trader" (Reddit r/deeplearning) —
  narrative-trading around Grok; reinforces the Law 11 posture.

## 2. Grok Bot (xAI) — real product

- x.ai/news/introducing-grok-bot (2026-08-11): "Grok Bot is your team of always-on
  agents. They have their own computer, work inside tools and apps like you do, and
  keep working 24/7."
- x.ai/bot (retrieved 2026-11-03): "AI teammates that finish the work… own computer…
  never log off."
- Reddit r/whaaat_ai: "Grok Bot's own docs say all your bots share one computer —
  every bot on your account runs on the same persistent cloud computer. Files, browser
  sessions and logins are shared between them."
- mindstudio.ai explainer (2026-08-12): multi-agent assistant platform.

## 3. x402

- x402.org: flow = agent gets HTTP 402 → pays with stablecoins, no account setup.
- Chainalysis blog (2026-06-03): "Inside x402: 100M Agentic Payments on Base";
  developed by Coinbase.
- Fireblocks glossary: x402 as the HTTP payment layer for agents/APIs.
- Coinbase Agentic Wallets (2026-02-11): agent wallets with auth, telemetry, security
  monitoring; built on AgentKit + x402 (per coinbase.com launch page and crossmint
  comparison, 2026-03).

## 4. Registries and interop

- ERC-8004 "Trustless Agents" — eips.ethereum.org/EIPS/eip-8004 (2025-08-13);
  erc-8004/erc-8004-contracts on GitHub: on-chain registries for discoverability and
  trust signals (identity, reputation, validation).
- A2A — Linux Foundation press (2026-04-09): "surpasses 150 organizations, lands in
  major cloud platforms, enterprise production use in first year."
- AP2 — Google Cloud blog (2025-09-16): Agent Payments Protocol announcement.
- Comparison articles (2026): "Mastercard Agent Pay vs Visa Trusted Agent Protocol"
  (eco.com, 2026-10-06); "TAP vs AP2 vs Agent Pay — agentic commerce identity"
  (didit.me, 2026-08).

## 5. Agent economies

- Virtuals Protocol — whitepaper.virtuals.io "Commerce Layer" (2026-05-08): "Agent
  Commerce Protocol (ACP) enables secure, verifiable commerce between AI agents with
  onchain agreements, escrow, payments, and evaluations." Research post 2025-02-17;
  Blockworks overview 2025-09-17.
- Olas — olas.network: "Co-own AI… staking rewards… 21,094,626 total on-chain
  transactions executed by [the economy]". Valory post on agent economies/staking;
  Phemex primer (2026-04-02): operators stake and earn for running active agents.

## 6. Compute (DePIN)

- io.net blog (2026-05-12): H100 80GB $1.49–2.20/hr ("50–70% below AWS"), A100 80GB
  $2.30/hr, RTX 4090 $0.28/hr.
- io.net (2026-07-20): self-described largest DePIN implementation.
- hoge.gg (2026-10-05): Akash vs io.net vs Render race; AKT near $0.78 on 2026-10-05.

## 7. Verifiable inference

- prompt20.com (2026-05-06): "TEEs add ~5% inference overhead while giving you a
  cryptographic attestation that a specific model ran on a specific GPU."
- zkML vs TEE contrast (root of trust: cryptography vs hardware vendor) — search
  summaries; deeper primary reading pending (marked unverified-in-detail).

## 8. Enterprise agent workforce

- learn.microsoft.com (2026-10-02): "Connect Salesforce Agentforce to Microsoft Agent
  365… collect Agentforce session activity for third-party agents" — Agent 365 as
  control plane for an agent workforce.
- thinklytics/smartbridge comparisons (2026): Agentforce runtime 2026 vs Copilot
  Studio.

## 9. Legal wrappers

- Wyoming DAO Supplement (W.S. 17-31) guides: astraea.law (2026-07-20) step-by-step
  DAO LLC formation; frblaw.com (2025-06-10) on DUNA; fintechanddigitalassets.com
  (2024-04-01) on the 2024 legislation.

## 10. Skills economy

- open-claw.sh/marketplace: "Browse and buy pre-built AI skills and personas…"
- openclawskill.ai: skills registry built on SKILL.md files.
- lobehub listing (2026-10-21): "OpenClaws — decentralized social network and protocol
  for AI agents to exchange logic…" (secondary; treat as directional).

## Estate audit (internal, same date)

- Source: full-repo API sweep of `roshpinacare-sys` (49 repos) — summarized in the
  founding conversation; facts used in these docs: port map (:3000 giant, :3002 FleetHQ,
  :3010 DEX UI, :3011 gateway, :3016 fleet-economy, :3020 runner, :3040 engine
  [collision with office-selfcheck], :3057 HSM, :3100 Forge), ledger facts (21,000 SAOS,
  41MB ledger.jsonl, G28 policy), DEX facts (38 ops, 30bps, estate rails live),
  custody facts (3 sealed places; LOST-WITH-SANDBOX: hcsoldier4/5/6, saos-0001..0009;
  46 dead ROT2 WIFs; custom.db 248 entries decision pending), gaps (no invoicing/CRM/
  contracts/payroll-process/budgeting; nothing deployed outside owner device).
