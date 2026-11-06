#!/usr/bin/env python3
"""dyn.ledger.v1 — the chain-wide work ledger and its checkpoints (gate 2.1).

The market's JSONL stream is an audit trail; this is the *chain*: every
lifecycle event across all job folders appended into one hash-chained ledger
(entries carry the exact µ¢ amounts, not floored USDS), sealed at fixed depth
into `dyn.checkpoint.v1` checkpoints — the DEX pulse pattern of specs/wire.md §4:

  - entries: {seq, day, kind, job_id, agent, body, prev, hash} where
    hash = object_hash({prev, seq, kind, day, body}) — tamper-evident by design;
  - merkle_root: over entry hashes (odd nodes duplicated, canonical pairing);
  - checkpoints: {height, day, seal, state_root, tx_root, witness_sigs} —
    tx_root over the sealed window, state_root over everything so far,
    ≥ threshold witness signatures (BFT ≤ 1 Byzantine with 7 active, 5 required);
  - the Law-19 dashboard line, exact at µ¢ resolution:
        emitted == settled_usds_muc * DYN_MU_PER_USDS_MUC   (400 µ per µ¢)
    the residue the floored stream leaves (400.51 vs 400.00) disappears here.

Witness signatures here are domain-hash stand-ins (deterministic, verifiable);
real ed25519-via-HSM signatures are the gate-2.1 hardening step — the shape,
threshold and fail-closed verification are already the protocol's.

  python3 dyn_ledger.py from-stream market.jsonl
  python3 dyn_ledger.py verify ledger.jsonl

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.canonical import object_hash  # noqa: E402
from dynamis_core.emission import DYN_MU_PER_USDS_MUC  # noqa: E402

LEDGER = "dyn.ledger.v1"
CHECKPOINT = "dyn.checkpoint.v1"
GENESIS = "0" * 64
SEAL_EVERY = 12          # sealed every 12 entries — the spec's seal cadence
ACTIVE_WITNESSES = 7
BFT_THRESHOLD = 5        # ≥ 5 of 7: BFT ≤ 1 Byzantine with 7
WITNESSES = tuple(f"witness-{i}" for i in range(1, ACTIVE_WITNESSES + 1))
SIG_DOMAIN = "dyn.checkpoint.sig"
KINDS = ("open", "work", "check", "refine", "settle", "refund", "post",
         "witness", "anchor", "approve", "dispute", "bid", "award", "stake")


# --------------------------------------------------------------------------
# the ledger
# --------------------------------------------------------------------------
class WorkLedger:
    """One append-only hash chain over the economy's work events."""

    def __init__(self, *, seal_hook=None) -> None:
        """seal_hook(checkpoint) fires whenever a full SEAL_EVERY window
        completes — the app uses it to keep the chain's seals on record as
        the events happen, so a later rewrite faces an anchor it held."""
        self.entries: list[dict] = []
        self.seal_hook = seal_hook

    def append(self, *, day: int, kind: str, job_id: str, agent: str,
               **body) -> dict:
        if kind not in KINDS:
            raise ValueError(f"unknown ledger kind: {kind}")
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        entry = {"seq": len(self.entries), "day": day, "kind": kind,
                 "job_id": job_id, "agent": agent, "body": body, "prev": prev}
        entry["hash"] = object_hash({"prev": prev, "seq": entry["seq"],
                                     "kind": kind, "day": day, "body": body})
        self.entries.append(entry)
        if self.seal_hook is not None and len(self.entries) % SEAL_EVERY == 0:
            self.seal_hook(self.checkpoint(day=day))
        return entry

    # ---------- integrity ----------
    def verify_chain(self) -> dict:
        """Recompute every hash and link. Returns {ok, depth, first_bad}."""
        prev = GENESIS
        for e in self.entries:
            want = object_hash({"prev": e["prev"], "seq": e["seq"],
                                "kind": e["kind"], "day": e["day"],
                                "body": e["body"]})
            if e["prev"] != prev or e["hash"] != want:
                return {"ok": False, "depth": e["seq"], "first_bad": e["hash"]}
            prev = e["hash"]
        return {"ok": True, "depth": len(self.entries), "first_bad": None}

    # ---------- sealing ----------
    def merkle_root(self, hashes: list[str]) -> str:
        if not hashes:
            return GENESIS
        level = list(hashes)
        while len(level) > 1:
            if len(level) % 2:
                level.append(level[-1])          # odd node duplicated
            level = [object_hash([level[i], level[i + 1]])
                     for i in range(0, len(level), 2)]
        return level[0]

    def inclusion_proof(self, seq: int) -> list[str]:
        """The siblings needed to prove entries[seq] is in the chain's root —
        the receipt a settler hands the buyer's auditor. Same pairing rule as
        merkle_root (odd node duplicated)."""
        hashes = [e["hash"] for e in self.entries]
        i = next(i for i, e in enumerate(self.entries) if e["seq"] == seq)
        proof: list[str] = []
        level = list(hashes)
        while len(level) > 1:
            if len(level) % 2:
                level.append(level[-1])
            if i % 2:
                proof.append({"s": level[i - 1], "side": "left"})
            else:
                proof.append({"s": level[min(i + 1, len(level) - 1)],
                              "side": "right"})
            level = [object_hash([level[j], level[j + 1]])
                     for j in range(0, len(level), 2)]
            i //= 2
        return proof

    @staticmethod
    def verify_inclusion(entry_hash: str, proof: list[str], root: str) -> bool:
        """Recompute the root from the leaf and its siblings — anyone with
        the proof and the root, no ledger access needed."""
        h = entry_hash
        for step in proof:
            sib = step["s"]
            h = object_hash([sib, h] if step["side"] == "left" else [h, sib])
        return h == root

    def all_checkpoints(self, *, day: int = 0,
                        witnesses: tuple[str, ...] = WITNESSES,
                        threshold: int = BFT_THRESHOLD) -> list[dict]:
        """One checkpoint per full window: 12, 24, 36 … entries covered."""
        cps = []
        for k in range(1, len(self.entries) // SEAL_EVERY + 1):
            covered = k * SEAL_EVERY
            window = self.entries[covered - SEAL_EVERY:covered]
            state_root = self.merkle_root(
                [e["hash"] for e in self.entries[:covered]])
            cps.append({
                "checkpoint": CHECKPOINT,
                "height": covered,
                "day": day,
                "seal": SEAL_EVERY,
                "state_root": state_root,
                "tx_root": self.merkle_root([e["hash"] for e in window]),
                "witness_sigs": [{"w": w, "s": _witness_sig(w, covered, state_root)}
                                 for w in witnesses[:threshold]],
            })
        return cps

    def checkpoint(self, *, day: int, witnesses: tuple[str, ...] = WITNESSES,
                   threshold: int = BFT_THRESHOLD) -> dict | None:
        """Seal the latest full window — None if no full window exists yet."""
        cps = self.all_checkpoints(day=day, witnesses=witnesses,
                                   threshold=threshold)
        return cps[-1] if cps else None

    # ---------- Law 19, exact ----------
    def invariant(self) -> dict:
        """emitted == revenue-verified, at µ¢ resolution, from the ledger alone.
        Settled revenue = payout + fee — the whole escrow that moved."""
        settled_muc = sum(e["body"].get("payout_muc", 0) + e["body"].get("fee_muc", 0)
                          for e in self.entries if e["kind"] == "settle")
        emitted_mu = sum(e["body"].get("emitted_dyn_mu", 0)
                         for e in self.entries if e["kind"] == "settle")
        refunds = [e for e in self.entries if e["kind"] == "refund"]
        return {
            "settled_usds_muc": settled_muc,
            "emitted_dyn_mu": emitted_mu,
            "expected_dyn_mu": settled_muc * DYN_MU_PER_USDS_MUC,
            "emitted_eq_revenue": emitted_mu == settled_muc * DYN_MU_PER_USDS_MUC,
            "refund_emits_nothing": all(
                e["body"].get("emitted_dyn_mu", 0) == 0 for e in refunds),
            "rate": DYN_MU_PER_USDS_MUC,
        }


def _witness_sig(witness: str, height: int, state_root: str) -> str:
    """HSM stand-in: deterministic domain hash over (witness, height, root).
    Real ed25519-via-HSM signatures are the gate-2.1 hardening step."""
    return object_hash({"d": SIG_DOMAIN, "w": witness,
                        "height": height, "state_root": state_root})


def verify_checkpoint(cp: dict, ledger: WorkLedger, *,
                      threshold: int = BFT_THRESHOLD) -> dict:
    """Fail-closed: roots must recompute, sigs must match and meet BFT count."""
    sealed = cp["height"]
    if sealed == 0 or sealed % SEAL_EVERY or sealed > len(ledger.entries):
        return {"ok": False, "why": "bad height"}
    if cp["state_root"] != ledger.merkle_root(
            [e["hash"] for e in ledger.entries[:sealed]]):
        return {"ok": False, "why": "state_root mismatch"}
    window = ledger.entries[max(0, sealed - SEAL_EVERY):sealed]
    if cp["tx_root"] != ledger.merkle_root([e["hash"] for e in window]):
        return {"ok": False, "why": "tx_root mismatch"}
    sigs = cp["witness_sigs"]
    if len(sigs) < threshold:
        return {"ok": False, "why": f"only {len(sigs)} sigs — BFT needs {threshold}"}
    for s in sigs:
        if s["s"] != _witness_sig(s["w"], sealed, cp["state_root"]):
            return {"ok": False, "why": f"witness sig invalid: {s['w']}"}
    return {"ok": True, "why": None}


# --------------------------------------------------------------------------
# building the ledger from a market stream
# --------------------------------------------------------------------------
def load_rows(path: str | Path) -> list[dict]:
    """Event rows from a market/ledger JSONL (skips summary/checkpoint rows)."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if "event" in obj:
                rows.append(obj)
    return rows


def ledger_from_rows(rows: list[dict]) -> WorkLedger:
    """Replay a dyn.market.v1 stream (exact-µ¢ fields) into a WorkLedger."""
    led = WorkLedger()
    carry = {"payout_muc", "fee_muc", "emitted_dyn_mu", "escrow_back_muc",
             "value_muc", "sha256", "overall", "value_usds", "count",
             "cls", "note", "sampled", "leader", "matches", "forged",
             "reason"}
    for r in rows:
        body = {k: v for k, v in r.items()
                if k not in ("day", "event", "job", "agent") and k in carry}
        led.append(day=r["day"], kind=r["event"], job_id=r.get("job", "-"),
                   agent=r.get("agent", "-"), **body)
    return led


def report(led: WorkLedger, cps: list[dict]) -> str:
    v = led.verify_chain()
    inv = led.invariant()
    lines = [
        f"{LEDGER} — {len(led.entries)} entries, chain ok: {v['ok']}",
        f"  kinds: " + ", ".join(
            f"{k}={sum(1 for e in led.entries if e['kind'] == k)}"
            for k in KINDS),
        f"  checkpoints: {len(cps)} sealed (every {SEAL_EVERY} entries, "
        f"{BFT_THRESHOLD}-of-{ACTIVE_WITNESSES} witness sigs)",
        f"  Law 19 exact: emitted {inv['emitted_dyn_mu']:,} µDYN == "
        f"{inv['settled_usds_muc']:,} µ¢ × {inv['rate']} → "
        f"{inv['emitted_eq_revenue']}",
        f"  refund emits nothing: {inv['refund_emits_nothing']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dyn_ledger", description="DYNAMIS work ledger (dyn.ledger.v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("from-stream")
    p.add_argument("stream", help="market JSONL (exact-µ¢ rows)")
    p.add_argument("--out", default=None, help="write ledger JSONL here")
    p = sub.add_parser("verify")
    p.add_argument("ledger", help="ledger JSONL")
    a = ap.parse_args(argv)

    if a.cmd == "from-stream":
        rows = load_rows(a.stream)
        led = ledger_from_rows(rows)
        cps = led.all_checkpoints(day=rows[-1]["day"] if rows else 0)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                for e in led.entries:
                    f.write(json.dumps(e, sort_keys=True) + "\n")
                for cp in cps:
                    f.write(json.dumps({"checkpoint": cp}, sort_keys=True) + "\n")
        print(report(led, cps))
        if a.out:
            print(f"  ledger: {a.out}")
        return 0

    led, cps = WorkLedger(), []
    with open(a.ledger, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if "checkpoint" in obj:
                cps.append(obj["checkpoint"])
            else:
                led.entries.append(obj)
    print(report(led, cps))
    bad = [c for c in cps if not verify_checkpoint(c, led)["ok"]]
    print(f"  checkpoint verification: {len(cps) - len(bad)}/{len(cps)} ok"
          + (f" — FAILED: {[verify_checkpoint(c, led)['why'] for c in bad]}"
             if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
