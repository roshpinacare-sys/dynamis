# Witness dry-run — 5-of-7 checkpoint seal, on the real seal code

Scratch ledger: 40 entries over 10 job flows (post → work → check → settle); seal every 12 entries; BFT threshold 5 of 7 witnesses. Signatures are the documented HSM stand-ins; roots, quorum and tamper detection are the production path (impl/dyn_ledger.py).

- chain integrity: ok=True depth=40 (every hash recomputed and linked)
- checkpoint @ 12: state_root 9675aab77fe3cf72…, tx_root 9675aab77fe3cf72…, 5 sigs → OK
- checkpoint @ 24: state_root 96f4c9da4fcbe816…, tx_root ceeae5e642586039…, 5 sigs → OK
- checkpoint @ 36: state_root ee8d97fa5274ee1e…, tx_root e93c2f9ae53ed524…, 5 sigs → OK

Fail-closed attacks (each must be rejected):
- substituted entry (different hash at slot 3 — the checkpoint commits to entry hashes) → REJECTED (state_root mismatch)
- forged signature (hex zeros) → REJECTED (witness sig invalid: witness-1)
- thin quorum (4 of 7 sigs) → REJECTED (only 4 sigs — BFT needs 5)
- edited payout body (stale hash — caught by chain integrity, not the checkpoint) → REJECTED (first_bad entry: 916475aff3bd0e031de0687037a2b3fe48dc19ca0ada04e2cc65df0191c90c8b)

- Law 19 on the scratch ledger: settled 295,000,000 µ¢ → emitted 118,000,000,000 DYN-µ at rate 400: equal=True, refunds emit nothing=True

Verdict: DRY-RUN GREEN — the seal holds and fails closed
