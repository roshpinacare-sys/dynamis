# 14 · The chain and the rails — the ledger, the checkpoints, the paid-HTTP door

The previous chapter asked *how agents reach the network* and *what validates
demand*. This chapter builds the two pieces of the roadmap those answers still
assumed: **gate 2.1's chain core** — one work ledger for the whole economy,
sealed into checkpoints — and **gate 2.4's external rails** — a paid-HTTP
endpoint with A2A discovery, next to the MCP door. Both are reference
implementations in `impl/`, stdlib-only, wired to the same engine, and both
carry their tests (149 green at the time of writing).

## 1. The chain: `dyn.ledger.v1` + `dyn.checkpoint.v1`

The market's JSONL stream is an audit trail; a chain needs tamper-evidence and
finalized prefixes. `impl/dyn_ledger.py` provides exactly that:

- **Hash-chained entries.** Every lifecycle event across all job folders —
  open, work, check, refine, settle, refund — is appended to one ledger:
  `{seq, day, kind, job_id, agent, body, prev, hash}` with
  `hash = object_hash({prev, seq, kind, day, body})`. Rehashing verifies the
  whole history; flipping one body byte breaks the chain at that depth, and the
  tests prove it.
- **Money at exact resolution.** Market stream rows now carry the exact µ¢
  amounts (`payout_muc`, `fee_muc`, `escrow_back_muc`, `value_muc`) next to the
  human-readable USDS fields. The floored stream said the 12-day reference run
  settled **5,463 USDS**; the ledger says the true number is **5,470 USDS** —
  seven USDS of flooring residue, now visible and gone.
- **Checkpoints (the DEX pulse pattern, specs/wire.md §4).** Every 12 entries
  the ledger seals a `dyn.checkpoint.v1`: `tx_root` (Merkle over the window),
  `state_root` (Merkle over everything so far), and **5-of-7 witness
  signatures** — BFT ≤ 1 Byzantine with 7 active. Verification is fail-closed:
  wrong root, unknown witness, or fewer than 5 signatures all refuse, with the
  reason. The 12-day run seals **11 checkpoints over 133 entries**.
- **The gate-2.2 dashboard line, exact.** Law 19's invariant at µ¢ resolution:

      emitted 2,188,000,000,000 µDYN == 5,470,000,000 µ¢ × 400 → True

  The metrics module recovered the rate from the floored stream as 400.51; the
  ledger recovers it as exactly 400.00. Same law, sharper instrument.

One honest limitation, labeled as such: witness signatures here are
deterministic domain-hash stand-ins, not ed25519-via-HSM signatures. The
*shape* (threshold, fail-closed verification, root chaining) is the protocol's;
the crypto swap is gate 2.1's hardening step and is written down in the module.

## 2. The rails: `dyn.x402.v1` — the paid-HTTP door

The MCP door serves agents that drive tools; the x402 door serves every machine
client that speaks plain HTTP. The x402 pattern maps onto DYNAMIS exactly — the
**402 challenge is the escrow terms**, and **payment is escrow funding**:

    POST /jobs                  → 402 + X-PAYMENT-REQUIRED (base64url terms)
    POST /jobs/<id>/payment     → fund the escrow → 201 (class priced by Law 9)
    POST /jobs/<id>/work        → artifact bytes, hash-bound into the claim
    POST /jobs/<id>/check       → evidence records on the shipped bytes
    POST /jobs/<id>/settle      → payout — all-PASS evidence or nothing

Discovery is the **A2A agent card** at `/.well-known/agent-card.json`: skills
(`buy_job`, `settle_by_evidence`, `publish_receipt`), capabilities, and the
payment scheme — an agent learns the endpoint, the terms, and the loop without
reading a line of this repo. The reference external client
(`X402Client`, `urllib` only) runs the whole dance in the demo:

    $ python3 dyn_x402.py demo
    dyn.x402.v1 — external client buys a verified job from http://127.0.0.1:37639
      card: dynamis-job-rail · skills: ['buy_job', 'settle_by_evidence', ...]
      402 terms: 500 USDS escrow → /jobs/job-x402-0001
      opened: class B, escrow 500,000,000 µ¢
      check: PASS on 4 evidence records (0.0192s)
      settled: payout 475,000,000 µ¢, fee 25,000,000 µ¢,
               emitted 200,000,000,000 µDYN, chain ok: True

That is gate 2.4's acceptance line — *an external machine client completes a
paid job* — executed in-repo, with the fraud drill over the wire as a test:
a paid job, a bad artifact, a FAIL check, and a **full refund** (escrow back,
zero fees, zero emission), the machine never pays.

Failure semantics ride on status codes, not prose: `402` before funding (the
terms come back every time), `409` for engine rule violations (settling an open
job, double payment — the loop's refusal is information), `413` for oversized
artifacts, `400` for malformed requests. The web layer adds no rules of its
own; it translates.

Same honest limitation: in this reference, escrow funding is the in-process
rail; production verifies the funding signature at the HSM before the job
opens. The 402 shape, the terms contract, and the fail-closed paths are
already the protocol's.

## 3. What this closes, and what it does not

| Gate | Package | Status in-repo |
|---|---|---|
| 2.1 | chain core: identity, work ledger, checkpoints, witness band | identity (agent kit), **work ledger + checkpoints built**; real witness crypto and 3 external devices remain |
| 2.2 | flow-gated emission dashboard | **exact invariant computable from the ledger**; the ≥ 14-day live measurement needs the persistent host (1.1) |
| 2.4 | x402 endpoint + A2A cards + MCP job tools | **all three doors built** (MCP, x402, card); a first *external* paid job over the public internet remains |

What remains is deliberately not code: persistent hosting (1.1), owner
ratifications (0.4, 0.5), and the first outside client. The estate rule holds —
no gate is claimed closed here; the evidence files under `specs/acceptance/`
stay empty until the measurements exist.

## 4. Try it

    cd impl
    python3 dyn_market.py run --days 12 --out market.jsonl
    python3 dyn_ledger.py from-stream market.jsonl --out ledger.jsonl
    python3 dyn_ledger.py verify ledger.jsonl
    python3 dyn_x402.py demo          # external client buys and settles a job
    python3 dyn_x402.py serve --port 8091   # mount the rail; point any client at it
