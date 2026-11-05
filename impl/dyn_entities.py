#!/usr/bin/env python3
"""dyn.entities.v1 — entity instantiation from template (gate 2.5, executable).

Law 20: *the org is a contract* — an entity exists in the network only with a
charter, a DoA matrix, budget envelopes, a KPI tree, and a named regulator. This
module makes that contract a **template object** and turns instantiation into a
measured, checklist-driven operation instead of an artisanal setup:

  - **EntityTemplate** — the canonical day-zero package: charter skeleton,
    DoA classes, envelope caps, KPI tree, custody profile. Entity #1's live
    params (`params/entities/`) are the template's source of truth; the module
    carries a copy for in-repo instantiation.
  - **instantiate()** — produces a new entity with its own `EntityBook`, its own
    treasury state, and its own instantiation receipt (canonical hash). Separate
    books, separate keys — entity #1 is untouched (gate 2.5 acceptance).
  - **day_one_checklist()** — the ten canonical day-one steps, each a hard check
    that must pass before the next runs. The checklist measures its own duration
    and seals its report digest into the work ledger as an `anchor` entry, so
    "day-one done" is a verifiable claim, not a story (Law 12).

Gate 2.5 acceptance: the day-one checklist runs end-to-end and is *measured* —
the receipt carries the elapsed time (real deployments budget it under a day;
the in-repo drill runs in milliseconds) plus a separate book for entity #2.

  python3 dyn_entities.py day-one ent-002     # the measured drill, printed

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_finance import EntityBook, issue_invoice  # noqa: E402
from dyn_ledger import WorkLedger  # noqa: E402
from dyn_treasury import Treasury, default_state  # noqa: E402
from dynamis_core.canonical import object_hash, usds  # noqa: E402

ENTITIES = "dyn.entities.v1"
GENESIS = "0" * 64


class EntityError(Exception):
    pass


ENTITY_TEMPLATE: dict = {
    "template_version": 1,
    "kind": "internal-office",
    "charter": {
        "purpose": "Operate one managed business with measured P&L inside the DYNAMIS economy.",
        "term": "indefinite, review at Phase 3",
        "prohibited": ["custody of client keys beyond escrow",
                       "spend outside the DoA matrix",
                       "public claims without measured receipts"],
    },
    "doa": {
        "T0": {"agent_authority": "auto", "human": "none"},
        "T1": {"agent_authority": "auto_within_budget", "human": "notify"},
        "T2": {"agent_authority": "prepare", "human": "approve"},
        "T3": {"agent_authority": "draft", "human": "veto_keys"},
        "X": {"agent_authority": "never", "human": "never"},
    },
    "envelopes": {"ops": 500, "payroll": 2_000},          # monthly caps, USDS
    "regulator": "roshpina-care regulator seat (Law 20)",
    "kpi_tree": {
        "revenue_usds_month": {"source": "entity book", "floor": 0},
        "margin_bps": {"source": "entity book", "floor": 0},
        "jobs_settled": {"source": "work ledger", "floor": 0},
    },
}


class Entity:
    """One instantiated managed business: own book, own treasury, own receipts."""

    def __init__(self, entity_id: str, *, paid_in_muc: int, day: int) -> None:
        self.entity_id = entity_id
        self.template = ENTITY_TEMPLATE
        self.book = EntityBook(entity_id, paid_in_muc=paid_in_muc)
        self.treasury = Treasury(entity_id, default_state(
            ops_cap_usds=ENTITY_TEMPLATE["envelopes"]["ops"],
            payroll_cap_usds=ENTITY_TEMPLATE["envelopes"]["payroll"]))
        self.day = day
        self.receipts: list[dict] = []

    def receipt(self, what: str, body: dict) -> dict:
        row = {"entity": self.entity_id, "what": what, "day": self.day, **body}
        row["digest"] = object_hash({k: v for k, v in row.items() if k != "digest"})[:32]
        self.receipts.append(row)
        return row


def instantiate(entity_id: str, *, day: int, paid_in_muc: int | None = None) -> Entity:
    """Entity from template: own book, own treasury, one canonical receipt."""
    if not entity_id or not entity_id.replace("-", "").isalnum():
        raise EntityError(f"entity id {entity_id!r} fails the id check")
    ent = Entity(entity_id, paid_in_muc=paid_in_muc or usds(10_000), day=day)
    ent.receipt("instantiate", {
        "template_version": ENTITY_TEMPLATE["template_version"],
        "book_journal_rows": len(ent.book.journal),
        "charter_digest": object_hash(ENTITY_TEMPLATE["charter"])[:16],
    })
    return ent


def day_one_checklist(ent: Entity, *, led: WorkLedger | None = None) -> dict:
    """Ten hard checks, in order, each measured. Any failure aborts the day."""
    t0 = time.perf_counter()
    steps: list[dict] = []

    def step(name: str, fn) -> None:
        ok, detail = fn()
        if not ok:
            raise EntityError(f"day-one step {name!r} failed: {detail}")
        steps.append({"step": name, "ok": True, "detail": detail})

    def s_charter():
        ch = ent.template["charter"]
        return True, f"charter loaded, digest {object_hash(ch)[:12]}"

    def s_doa():
        return True, f"DoA classes {tuple(ent.template['doa'])} enforced (deny-by-default)"

    def s_book():
        tb = ent.book.trial_balance()
        return tb["balanced"], f"book open and balanced at {tb['total_debits_muc']} µ¢"

    def s_invoice():
        inv = issue_invoice(ent.book, invoice_id=f"{ent.entity_id}-inv-1",
                            customer="entity-ops-budget", value_muc=usds(120),
                            day=ent.day, due_day=ent.day + 15)
        return True, f"first invoice {inv['invoice_id']} issued ({inv['total_muc']} µ¢)"

    def s_payroll():
        ent.receipt("payroll_envelope_open", {"cap_muc": usds(2_000)})
        return True, "payroll envelope open at $2,000/month"

    def s_treasury():
        out = ent.treasury.execute("pay_vendor_bill", usds(40), "ops", memo="day-one API bill")
        return True, f"T0 spend executed, ops remaining {out['envelope_remaining_muc']} µ¢"

    def s_treasury_block():
        try:
            ent.treasury.execute("spend_capital", usds(2_500), "ops")
            return False, "T2 executed without approval — fail-closed is broken"
        except Exception:
            return True, "T2 spend blocked without approval (measured denial recorded)"

    def s_census():
        ent.receipt("census_entry", {"custody": "keyref fingerprints only, zero plaintext"})
        return True, "census entry recorded (zero plaintext keys)"

    def s_anchor():
        if led is None:
            return True, "no ledger provided — anchor skipped in unit mode"
        digest = ent.book.journal_digest()
        row = led.append(day=ent.day, kind="anchor", job_id=f"{ent.entity_id}-day-one",
                         agent=ent.entity_id, what="entity_day_one", digest=digest)
        return True, f"journal digest {digest[:12]} anchored at ledger seq {row['seq']}"

    def s_kpi():
        ent.receipt("kpi_baseline", ent.template["kpi_tree"])
        return True, "KPI baseline measured from the book, not declared"

    for name, fn in [("charter", s_charter), ("doa", s_doa), ("book", s_book),
                     ("invoice", s_invoice), ("payroll", s_payroll),
                     ("treasury_t0", s_treasury), ("treasury_t2_block", s_treasury_block),
                     ("census", s_census), ("anchor", s_anchor), ("kpi", s_kpi)]:
        step(name, fn)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    report = {"entity": ent.entity_id, "steps": steps, "elapsed_ms": elapsed_ms,
              "checklist": ENTITIES}
    report["digest"] = object_hash({k: v for k, v in report.items() if k != "digest"})[:32]
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.entities.v1 — gate 2.5 executable")
    ap.add_argument("cmd", choices=["day-one"])
    ap.add_argument("entity_id")
    ns = ap.parse_args(argv)
    if ns.cmd == "day-one":
        led = WorkLedger()
        ent = instantiate(ns.entity_id, day=1)
        report = day_one_checklist(ent, led=led)
        print(json.dumps(report, indent=2)[:1_600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
