# Wire spec — bytes, ops, signatures, checkpoints

Normative for anything that crosses a process, machine, or chain boundary. The
executable half of this file is `impl/dynamis_core/canonical.py` (61-test suite
passing). Precedence: measured reality > `params/genesis.yaml` > `CANON.md` > this file.

## 1. Canonical serialization (ADR-0007)

Every signed or hashed payload is canonical JSON bytes:

- keys sorted bytewise (UTF-16-unaware, plain lexicographic), tight separators (`,`/`:`),
  no whitespace, UTF-8, no escaped `/`;
- **integers only** — a float anywhere in the tree is a hard error (the µ¢ convention:
  1 µ¢ = 10⁻⁶ USDS; dollar literals in code are written `usds(n)` only);
- dataclasses/structs serialize as plain objects; tuples as arrays;
- `hash(x) = sha256(canon(x))` in hex; `sig_domain(x) = sha256(canon({"dyn_domain": D, "payload": x}))`.

Domains in force (extending the list requires an ADR):

| Domain | Signs |
|---|---|
| `dyn.receipt.v1` | runner receipts (schemas/receipt.schema.json) |
| `dyn.job.transition.v1` | escrow state-machine events |
| `dyn.checkpoint.v1` | witness-signed state roots (§4) |
| `dyn.pricefeed.v1` | witness price samples |
| `dyn.id.v1` | cross-network identity proofs (`saos.id.v1` shape) |

A signature over one domain never verifies in another — replay across object types is
designed out, not policed.

## 2. Chain ops (custom_json v1)

DYNAMIS genesis runs as **checkpointed audit ledger** anchored to existing rails
(ADR-0006), not a full L1. Ops ride the estate's live `custom_json` pattern
(`saos.id.v1`, DEX relay) with id `dyn.v1`:

```
{ "id": "dyn.v1",
  "json": { "op": "job.fund", "v": 1,
            "job": "job-alpha-1", "escrow_usds_muc": 500000000,
            "revenue_ref": "env-ops-001", "nonce": 17 } }
```

| op | actor | guards (fail-closed) |
|---|---|---|
| `agent.register` | agent | agent.schema.json valid; census fresh; ≥ 1 HSM keyref |
| `job.open` | entity persona | job.schema.json valid; DoA check T1 passed; class ≥ floor_class |
| `job.fund` | entity persona | escrow > 0; budget envelope holds; rail caps hold |
| `job.claim` | worker | funder ≠ worker; worker census fresh; RC²/fee requirements met |
| `job.deliver` | worker | claim.schema.json valid; receipt domain `dyn.receipt.v1` verifies |
| `job.verify` | witness band | ladder run posted; class C default for money jobs |
| `job.settle` | witness band | state = VERIFYING with pass verdict; emission recorded against `revenue_ref` |
| `job.refund` | anyone (timeout) | `now_day > deadline_day`; fee = 0 |
| `eval.post` | evaluator | eval.schema.json valid; bond ≥ class minimum |
| `checkpoint` | witness band | §4 format; BFT count met |
| `price.feed` | witness | `dyn.pricefeed.v1`; deviation beyond band → bond-burn flag |
| `compute.enroll` | provider | benchmark receipts attached; census fresh |

Op envelope rules: ≤ 2 KiB per op (custom_json practical limit); nothing secret ever
crosses (the fleet's regex-scrubbed MCP-output pattern is the baseline); one op = one
state transition = one deterministic validation.

## 3. Hash chains

Two chains, both sha256-linked, both re-derivable by anyone (Law 4):

1. **Event chain** (per job): `ev.hash = hash({prev, seq, kind, day, body})` —
   `impl/dynamis_core/escrow.py::verify_chain` re-derives it; tampering any field
   breaks every later link.
2. **Receipt chain** (per runner): `receipt.prev_receipt_hash` — the `:3020` pattern,
   formalized in schemas/receipt.schema.json.

Checkpointing (§4) anchors Merkle roots of both chain types to: (a) the fleet-economy
ledger (`:3016`, append-only with whole-chain `/verify`), (b) estate free
custom_json notary (~5,000 anchors/day capacity), (c) the ETH batch notary (~$0.10 per
batch) for high-value epochs. Anchors prove existence; the data stays at the root
(Law 16).

## 4. Checkpoints (the DEX pulse pattern)

3-second blocks, sealed every 12 blocks (~36 s) — the `saos-dex` seal cadence, already
measured in the estate. A sealed checkpoint:

```
{ "height": 28800, "day": 47, "seal": 2400,
  "state_root": "<64hex>",           // Merkle root over (event chains ∪ receipt chains ∪ accounts)
  "tx_root": "<64hex>",              // Merkle root over the 12 blocks' ops
  "witness_sigs": [ {"w": "witness-1", "s": "<96hex>"}, ... ]   // ≥ 5 of 7 active
}
```

- **Finality**: ≥ 5 of 7 active witness signatures (BFT ≤ 1 Byzantine with 7; standby
  promotion on miss — docs/03 §2).
- Anchoring: the epoch seal (every 2,400 checkpoints ≈ 24 h) goes to the anchor rails.
- Fork handling: genesis era has one sequencer (the witness band leader by VRF order);
  a forked root that cannot gather 5-of-7 halts the chain fail-closed — no minority fork
  ever finalizes. Progression to full BFT is a Phase-3+ ADR, not an assumption.

## 5. Identifiers and time

- IDs: `^[a-z0-9][a-z0-9-]{2,63}$` (ULID-compatible prefix style: `job-`, `cl-`,
  `ev-`, `ent-`, `pw-`, `agent-`).
- Protocol day = integer, increments at 00:00 UTC. Deadlines, census freshness,
  anti-herd schedules (`mulberry32(day|account)`) all key off it — one clock, no drift.
- Human-readable timestamps in off-chain records are ISO-8601 UTC only.

## 6. Transport security

- Value-signing only through HSM `:3057` (`/sign {keyRef, digestHex}`, deny-by-default);
  agents hold capabilities, never keys (Law 3, AGENTS.md §3).
- x402 endpoints speak HTTP 402 + USDS; A2A cards publish capability scopes; MCP tools
  stay regex-scrubbed. All external surfaces honor the kill-switch rule: every service
  ships with an armed, tested kill switch (AGENTS.md §3.7).
