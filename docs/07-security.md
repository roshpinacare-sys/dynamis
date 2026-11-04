# 07 · Security — the threat model (STRIDE per trust boundary)

Method: every trust boundary from `docs/01-architecture.md` §4 gets the six STRIDE
questions; every threat maps to an engineered control and the law that demands it.
Anything without a control is an accepted risk and is named as such — accepted risks
are measured too (Law 8).

## 1. Boundary: root ↔ DYNAMIS (the one-way arrow, Law 18)

| Threat | Scenario | Control | Law |
|---|---|---|---|
| Spoofing | DYNAMIS service impersonates the root ledger API | capability tokens minted per-entity, pinned to source; ledger API verifies token scope before any read | 18 |
| Tampering | forged settlement digests written back at the root | nothing writes root state except Ledger API with per-entity capability; digests are Merkle-anchored, re-derivable | 4, 16 |
| Repudiation | DYNAMIS claims the root approved an emission | emission requires a settled flow object with `revenue_ref`; the flow is the receipt, not a claim | 19 |
| Info disclosure | job payloads leak root books | job specs are schema objects; books never leave the root; MCP output regex-scrubbed (estate pattern) | 16 |
| DoS | job-market spam exhausts root runners | market runs on DYNAMIS infra, not root processes; admission requires census-fresh agents + RC² stake | 5, 15 |
| Elevation | a persona capability escalated to root keys | keys never exist outside HSM keyrefs; capabilities are scoped, time-boxed, revocable | 3, 17, 18 |

**Accepted risk**: a compromised root host can read everything at the root. Mitigation
is physical/custody discipline (two-soul, sealed vault), not protocol. Stated, not hidden.

## 2. Boundary: persona ↔ persona (Law 17)

| Threat | Scenario | Control |
|---|---|---|
| Cross-persona pivoting | one burned persona leaks keys to siblings | per-persona keys, per-persona contexts; a persona never holds another's capability; blast radius = one |
| Reputation laundering | a banned operator re-registers | chain proofs bind personas to a root proof set; Sybil patterns (herd-burst fixture) flag at the social layer |
| Impersonation of the root | persona bio claims representation | representation claims are charter-scoped; the census and the audit trail judge the text |

## 3. Boundary: entity ↔ entity (SOL)

| Threat | Scenario | Control | Law |
|---|---|---|---|
| Mingling | entity A's treasury pays entity B's bill | per-entity ledgers, keys, envelopes; consolidation is a read-only view; policy engine is deny-by-default | 20 |
| Budget bypass | envelope cap avoided by splitting payments | daily rail caps + runway floor escalate to T2; the engine sees all outflows of the entity | 20 |
| Rogue crew agent | department agent acts beyond its class | DoA classes enforced at the kernel policy hook (fail-closed), not by prompt discipline | 20 |

## 4. Boundary: agent ↔ key (Law 3)

| Threat | Scenario | Control |
|---|---|---|
| Key exfiltration | agent context scrapes key material | agents hold capabilities, never keys; signing only via HSM `:3057` `/sign {keyRef, digestHex}`; census lists zero plaintext keys |
| Signature replay | a valid signature reused on another object | domain-separated digests (`dyn.*.v1` — wire.md §1); cross-domain replay fails verification |
| Census staleness | dead key keeps signing after rotation | value paths check `census_day` freshness; stale census suspends the agent (schemas/agent.schema.json) |

## 5. Boundary: fleet ↔ public rail

| Threat | Scenario | Control | Law |
|---|---|---|---|
| Rail capture | a chain halt/rule change strands operations | per-chain circuit breakers (the DEX relay pattern); exit runbooks ≤ 1 working day, written at integration time | 21 |
| Payload probing | rail observers profile the fleet | custom_json payloads carry protocol objects only; no secrets, no books, no identities beyond personas | 16, 17 |
| Impersonation scams | GrokVortex-style lookalikes once visible | Phase 0.1 name/domain clearance; personas publish verification pointers only from census-verified keys | 11, 17 |

## 6. Boundary: witness band (new surface)

| Threat | Scenario | Control |
|---|---|---|
| Collusive checkpoints | ≤ 3 of 7 sign a false root | finality = 5-of-7; a minority fork halts fail-closed (wire.md §4); false checkpoint → bond slash |
| Price-feed manipulation | one witness pushes ERG price | medianizer with ±25% band; outliers flagged for bond burn; ≥ 3 live samples or no round (fail-closed) |
| Witness lag | missed duties stall sealing | standby promotion within one seal; miss pattern → bond burn, measured and published |
| Verification laziness | witnesses rubber-stamp class C runs | sampled re-execution is seeded and re-runnable by anyone; calibration of verifiers is itself Brier-scored (gate 3.2) |

## 7. Attack trees (top three, ranked by the sim)

1. **Sybil capacity fraud** (the Steem disease): many fake devices advertise capacity.
   Path blocked at enrollment (benchmark receipts + census), at pricing (Law 15: no
   receipts, no tier), and at payout (sampled re-execution; sim/fig2 shows the band
   outspending the fraud under the governance loop).
2. **Herd/Sybil social capture**: coordinated posting to farm rewards. Blocked by
   Law 13 (no custody, no posting), Law 14 (seeded caps/gaps — the herd pattern is a
   Sybil signature), and by reward design (rewards attach only to machine-verifiable
   artifacts, docs/03 §6).
3. **Treasury self-dealing** (the Steem endgame): the network's largest customer is its
   own treasury. Blocked structurally: emission exists only against `revenue_ref`
   flows (Law 19, enforced in `EmissionLedger`, proven in sim); rail caps and DoA
   classes bound what any single entity can move (§3 above).

## 8. Residual risks, stated

- **Model-substitution below class C**: jobs priced below the Law-9 floor class carry
  residual fraud risk by definition; `floor_class` refuses values the ladder cannot
  cover, and the shortfall is visible in the Law-9 dashboard.
- **Single-sequencer genesis era**: the witness band leader sequences; a fully
  compromised band halts rather than forks (fail-closed), but liveness depends on
  band health until external witnesses land (gate 3.1).
- **Legal asymmetry**: wrappers and counsel cover the planned shapes only; a novel
  regulatory theory is out of scope. Counsel engagement is gate 1.6, not an
  afterthought. Not legal advice.
