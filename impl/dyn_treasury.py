#!/usr/bin/env python3
"""dyn.treasury.v1 — the treasury operations engine (gate 2.6, executable).

The kernel DoA engine (`dynamis_core.policy`) classifies and decides. This module
is the executive half: it turns decisions into recorded, hash-chained, fail-closed
operations on an entity's treasury (Law 20, docs/02 §1, §4):

  - **Decision journal (dyn.treasury.v1)** — every `evaluate()` result that the
    treasury acts on (or refuses) is one journal row: prev-hash chained, integers
    only (ADR-0007), rehash-verifiable. A denial is recorded with the same rigor
    as an approval — the audit trail never distinguishes them by omission.
  - **Execute is the only money path** — `execute()` re-runs the kernel decision
    at execution time (not the cached one), refuses on any denial, books the
    spend into the envelope state, and only then journals the row. TOCTOU on a
    treasury decision is a bug class, so it is closed by construction.
  - **Approvals are explicit** — T2 needs `human_approved=True` *at execute time*;
    T3 needs veto keys; X refuses always. "The engine said yes earlier" is never
    an authority.

Gate 2.6 acceptance: a T2 spend is blocked without regulator approval — measured
in `tests/test_dyn_treasury.py::test_t2_blocked_without_approval`.

  python3 dyn_treasury.py demo     # the measured drill, printed

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core import BudgetEnvelope, TreasuryState, evaluate, object_hash  # noqa: E402
from dynamis_core.canonical import usds  # noqa: E402

TREASURY = "dyn.treasury.v1"
GENESIS = "0" * 64


class TreasuryError(Exception):
    pass


class TreasuryJournal:
    """Hash-chained decision log. Append-only; every row rehash-verifies."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._prev = GENESIS

    def append(self, row: dict) -> dict:
        full = {"seq": len(self.rows), "prev": self._prev, **row}
        full["digest"] = object_hash({k: v for k, v in full.items() if k != "digest"})
        self.rows.append(full)
        self._prev = full["digest"]
        return full

    def verify(self) -> dict:
        prev = GENESIS
        for i, row in enumerate(self.rows):
            if row["seq"] != i or row["prev"] != prev:
                return {"ok": False, "at": i, "why": "chain break"}
            expect = object_hash({k: v for k, v in row.items() if k != "digest"})
            if row["digest"] != expect:
                return {"ok": False, "at": i, "why": "digest mismatch"}
            prev = row["digest"]
        return {"ok": True, "rows": len(self.rows)}


class Treasury:
    """One entity's spend authority. Deny-by-default end to end."""

    def __init__(self, entity_id: str, state: TreasuryState) -> None:
        self.entity_id = entity_id
        self.state = state
        self.journal = TreasuryJournal()

    def decide(self, kind: str, amount_muc: int, envelope: str = "ops", *,
               human_approved: bool = False, veto_keys: bool = False) -> dict:
        """Classify + evaluate through the kernel. Nothing is executed here."""
        d = evaluate(self.state, kind, amount_muc, envelope,
                     human_approved=human_approved, veto_keys=veto_keys)
        row = self.journal.append({
            "op": "decide", "entity": self.entity_id, "kind": kind,
            "amount_muc": amount_muc, "envelope": envelope,
            "allowed": d.allowed, "class": d.doa_class,
            "requires": d.requires, "reason": d.reason,
        })
        return {"decision": d.as_dict(), "row": row}

    def execute(self, kind: str, amount_muc: int, envelope: str = "ops", *,
                human_approved: bool = False, veto_keys: bool = False,
                memo: str = "") -> dict:
        """The only money path. Re-decides at execution time; refuses on denial."""
        d = evaluate(self.state, kind, amount_muc, envelope,
                     human_approved=human_approved, veto_keys=veto_keys)
        if not d.allowed:
            row = self.journal.append({
                "op": "execute_denied", "entity": self.entity_id, "kind": kind,
                "amount_muc": amount_muc, "envelope": envelope,
                "class": d.doa_class, "requires": d.requires, "reason": d.reason,
            })
            raise TreasuryError(json.dumps({"decision": d.as_dict(), "row_digest": row["digest"][:16]}))
        self.state.book_spend(envelope, amount_muc)
        row = self.journal.append({
            "op": "execute", "entity": self.entity_id, "kind": kind,
            "amount_muc": amount_muc, "envelope": envelope,
            "class": d.doa_class, "reason": d.reason, "memo": memo,
            "envelope_remaining_muc": self.state.envelopes[envelope].remaining_muc(),
        })
        return {"decision": d.as_dict(), "row": row,
                "spent_muc": amount_muc, "envelope_remaining_muc": self.state.envelopes[envelope].remaining_muc()}


def default_state(*, ops_cap_usds: int = 500, payroll_cap_usds: int = 2_000) -> TreasuryState:
    """The entity's envelope set, per doa-001 thresholds. Measured runway is fed in."""
    return TreasuryState(envelopes={
        "ops": BudgetEnvelope("ops", usds(ops_cap_usds), "monthly"),
        "payroll": BudgetEnvelope("payroll", usds(payroll_cap_usds), "monthly"),
    }, daily_spent_muc=0, runway_months=12.0)


def demo() -> str:
    """The gate-2.6 drill: T2 blocked without approval, allowed with it."""
    tr = Treasury("ent-001", default_state(ops_cap_usds=10_000))
    lines: list[str] = []
    try:
        tr.execute("spend_capital", usds(2_500), "ops")
        lines.append("UNEXPECTED: T2 spend executed without approval")
    except TreasuryError as exc:
        lines.append(f"T2 blocked without approval — measured: {exc.args[0][:80]}…")
    out = tr.execute("spend_capital", usds(2_500), "ops", human_approved=True,
                     memo="regulator-approved capital spend")
    lines.append(f"T2 allowed with approval: spent {out['spent_muc']} µ¢, "
                 f"ops envelope {out['envelope_remaining_muc']} µ¢ remaining")
    v = tr.journal.verify()
    lines.append(f"journal verify: {v}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.treasury.v1 — gate 2.6 executable")
    ap.add_argument("cmd", choices=["demo"])
    ns = ap.parse_args(argv)
    if ns.cmd == "demo":
        print(demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
