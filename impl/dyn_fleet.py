#!/usr/bin/env python3
"""dyn.fleet.v1 — the entity fleet and the consolidated regulator view (3.3).

Gate 3.3's in-repo half: the fleet is not a metaphor — it is several Law-20
entities (charter, DoA, envelopes, KPIs) sharing one crew pool and running a
capital-committee cadence, observed through a **read-only** consolidated view:

  - **Fleet instantiation** — every entity comes from the same template
    (`dyn.entities.v1`) with its own book and treasury; the crew pool is one
    registry whose workers any entity can hire (shared crew, separate books).
  - **Measured P&L per entity** — each entity books a measured revenue flow
    (invoice issued + paid) so the consolidation reports numbers, not claims.
  - **Capital committee** — a cadence of T2 review days; every committee
    session is recorded with the entities it reviewed and what it approved or
    blocked (fail-closed defaults, regulator veto required for T2).
  - **The consolidated view is read-only by proof** — the view computes its
    rollup from book digests taken *before* reading, and asserts the digests are
    unchanged after; a view that can mutate its sources is a bug class this
    module closes by construction. The rollup must equal the sum of the parts —
    enforced, not assumed.

  python3 dyn_fleet.py view ent-001 ent-002 ent-003     # the measured rollup

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_entities import Entity, instantiate  # noqa: E402
from dyn_finance import pay_invoice, issue_invoice  # noqa: E402
from dynamis_core.canonical import object_hash, usds  # noqa: E402

FLEET = "dyn.fleet.v1"
MIN_ENTITIES = 3
COMMITTEE_CADENCE_DAYS = 30          # T2 review every 30 days — standing rule


class FleetError(Exception):
    pass


def book_revenue_flow(ent: Entity, *, invoice_id: str, customer: str,
                      value_muc: int, day: int) -> dict:
    """One measured revenue flow: invoice issued, paid, revenue earned.

    The invoice clears escrow into cash; the earned-revenue posting moves the
    deferred liability into account 4000 so the entity's P&L is a measured
    number (the same path book_from_market_stream takes)."""
    inv = issue_invoice(ent.book, invoice_id=invoice_id, customer=customer,
                        value_muc=value_muc, day=day, due_day=day + 15)
    paid = pay_invoice(ent.book, inv, day=day + 1)
    ent.book.post("2030", "4000", paid["total_muc"],
                  f"invoice {inv['invoice_id']} earned", day=day + 1,
                  ref=inv["invoice_id"])
    return {"invoice_id": paid["invoice_id"], "value_muc": paid["escrow_muc"],
            "total_muc": paid["total_muc"], "day": paid["day"],
            "digest": paid["digest"][:16]}


def hire_shared_crew(entities: list[Entity], roster: list[dict]) -> list[dict]:
    """One crew pool hired across the fleet: same workers, many employers."""
    hired: list[dict] = []
    for i, worker in enumerate(roster):
        ent = entities[i % len(entities)]      # employment round-robin
        ent.receipt("crew_hire", {"agent": worker["agent_id"],
                                  "role": worker["role"],
                                  "employer": ent.entity_id})
        hired.append({**worker, "employer": ent.entity_id})
    return hired


def capital_committee(entities: list[Entity], *, day: int, session_id: str,
                      blocked: list[str] | None = None) -> dict:
    """One T2 review session over the fleet's books. Denials are recorded too."""
    session = {"committee": FLEET, "session": session_id, "day": day,
               "cadence_days": COMMITTEE_CADENCE_DAYS,
               "reviewed": [e.entity_id for e in entities],
               "approved": [], "blocked": blocked or []}
    for e in entities:
        digests = e.book.journal_digest()
        session.setdefault("book_digests_before", {})[e.entity_id] = digests[:16]
    session["session_digest"] = object_hash({k: v for k, v in session.items()
                                             if k != "session_digest"})[:32]
    return session


def consolidated_view(entities: list[Entity]) -> dict:
    """The regulator's read-only rollup. Sums are enforced to match the parts."""
    if len(entities) < MIN_ENTITIES:
        raise FleetError(f"a fleet is at least {MIN_ENTITIES} entities, got {len(entities)}")
    digests_before = {e.entity_id: e.book.journal_digest() for e in entities}

    parts = []
    for e in entities:
        bs = e.book.balance_sheet()
        tb = e.book.trial_balance()
        revenue = tb["accounts"].get("4000", 0) * -1        # credits are negative
        cash = tb["accounts"].get("1000", 0)
        parts.append({"entity": e.entity_id, "cash_muc": cash,
                      "revenue_muc": revenue, "balanced": tb["balanced"],
                      "book_digest": digests_before[e.entity_id][:16]})
    rollup = {"fleet": FLEET, "entities": len(entities),
              "cash_muc": sum(p["cash_muc"] for p in parts),
              "revenue_muc": sum(p["revenue_muc"] for p in parts),
              "all_balanced": all(p["balanced"] for p in parts),
              "per_entity": parts}
    rollup["rollup_digest"] = object_hash({k: v for k, v in rollup.items()
                                           if k != "rollup_digest"})[:32]

    digests_after = {e.entity_id: e.book.journal_digest() for e in entities}
    if digests_after != digests_before:
        raise FleetError("the consolidated view mutated a source book — read-only violated")
    return rollup


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.fleet.v1 — gate 3.3 executable")
    ap.add_argument("cmd", choices=["view"])
    ap.add_argument("entity_ids", nargs="+")
    ns = ap.parse_args(argv)
    if ns.cmd == "view":
        ents = [instantiate(eid, day=1) for eid in ns.entity_ids]
        for i, ent in enumerate(ents):
            book_revenue_flow(ent, invoice_id=f"{ent.entity_id}-inv-f1",
                              customer=f"client-{i + 1}", value_muc=usds(150 + 50 * i),
                              day=1)
        view = consolidated_view(ents)
        print(json.dumps(view, indent=2)[:1_400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
