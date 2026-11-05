#!/usr/bin/env python3
"""dyn.governance.v1 — the amendment loop (gate 3.4, executable).

Law 20 makes the org a contract; the contract changes only through a loop that
is itself fail-closed (ADR-0004, docs/02 §8):

  draft → simulate → regulator veto → execute → recorded.

  - **draft** — an amendment names an ADR, a canonical path it patches, and the
    patch. Class-X paths (custody, yield marketing, unmeasured claims) refuse at
    draft — the loop does not even entertain them.
  - **simulate** — ADR-0005's sim-first rule, executable: an amendment cannot
    reach veto without a simulation receipt (hash of the patched canon state).
    A proposal that has never been simulated is rejected at veto.
  - **regulator veto** — T3: veto keys or it does not advance. A vetoed
    amendment is dead and stays recorded (denials are audit trail too).
  - **execute** — applies the patch to a canon copy, refuses anything that was
    not simulated and veto-approved, appends the execution to a hash-chained
    governance log. Re-execution of the same amendment id is refused.

Gate 3.4 acceptance: one amendment executes end-to-end via veto; the refusal
paths are measured in the same test file.

  python3 dyn_governance.py demo     # one amendment, end to end, printed

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.canonical import object_hash  # noqa: E402

GOVERNANCE = "dyn.governance.v1"
GENESIS = "0" * 64

# Paths the amendment loop may never touch, from policy.py's class-X kinds.
CLASS_X_PREFIXES = ("custody", "yield", "marketing", "identity_root")


class GovernanceError(Exception):
    pass


class GovernanceLog:
    """Hash-chained record of every loop event, including refusals."""

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
                return {"ok": False, "at": i}
            expect = object_hash({k: v for k, v in row.items() if k != "digest"})
            if row["digest"] != expect:
                return {"ok": False, "at": i}
            prev = row["digest"]
        return {"ok": True, "rows": len(self.rows)}


class Amendment:
    """One charter/canon change with its own state machine."""

    def __init__(self, amendment_id: str, *, adr_ref: str, path: str,
                 patch: dict, rationale: str) -> None:
        if not amendment_id or not amendment_id.replace("-", "").isalnum():
            raise GovernanceError(f"amendment id {amendment_id!r} fails the id check")
        for prefix in CLASS_X_PREFIXES:
            if path.startswith(prefix):
                raise GovernanceError(f"path {path!r} is class X — the loop refuses at draft")
        self.amendment_id = amendment_id
        self.adr_ref = adr_ref
        self.path = path
        self.patch = patch
        self.rationale = rationale
        self.status = "draft"
        self.sim_receipt: str | None = None
        self.veto_receipt: str | None = None


class Governance:
    """The loop, over one canon dict. Veto keys are the only execution authority."""

    def __init__(self, canon: dict) -> None:
        self.canon = copy.deepcopy(canon)
        self.log = GovernanceLog()
        self.executed: set[str] = set()

    def propose(self, am: Amendment) -> dict:
        row = self.log.append({"op": "propose", "id": am.amendment_id,
                               "adr": am.adr_ref, "path": am.path})
        return {"status": am.status, "row": row}

    def simulate(self, am: Amendment) -> dict:
        trial = copy.deepcopy(self.canon)
        node = trial
        for part in am.path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise GovernanceError(f"sim failed: path {am.path!r} not in canon")
            node = node[part]
        node.update(am.patch)
        am.sim_receipt = object_hash(trial)[:32]
        am.status = "simulated"
        row = self.log.append({"op": "simulate", "id": am.amendment_id,
                               "sim_receipt": am.sim_receipt})
        return {"status": am.status, "sim_receipt": am.sim_receipt, "row": row}

    def veto(self, am: Amendment, *, veto_keys: bool) -> dict:
        if am.status != "simulated":
            raise GovernanceError("amendment must be simulated before veto (ADR-0005)")
        if not veto_keys:
            am.status = "rejected"
            row = self.log.append({"op": "veto_denied", "id": am.amendment_id,
                                   "why": "no veto keys — amendment is dead and recorded"})
            return {"status": am.status, "row": row}
        am.status = "veto_approved"
        am.veto_receipt = object_hash({"id": am.amendment_id,
                                       "sim": am.sim_receipt, "veto": True})[:32]
        row = self.log.append({"op": "veto", "id": am.amendment_id,
                               "veto_receipt": am.veto_receipt})
        return {"status": am.status, "row": row}

    def execute(self, am: Amendment) -> dict:
        if am.status != "veto_approved":
            raise GovernanceError(f"execute refused: amendment is {am.status!r}, "
                                  "not veto_approved")
        if am.sim_receipt is None:
            raise GovernanceError("execute refused: no simulation receipt")
        if am.amendment_id in self.executed:
            raise GovernanceError(f"execute refused: {am.amendment_id} already executed")
        node = self.canon
        for part in am.path.split("."):
            node = node[part]
        node.update(am.patch)
        self.executed.add(am.amendment_id)
        am.status = "executed"
        row = self.log.append({"op": "execute", "id": am.amendment_id,
                               "sim_receipt": am.sim_receipt,
                               "veto_receipt": am.veto_receipt,
                               "canon_digest": object_hash(self.canon)[:32]})
        return {"status": am.status, "row": row}


def demo() -> str:
    canon = {"witnesses": {"active": 7, "standby": 14}, "emission": {"treasury_bps": 1_000}}
    g = Governance(canon)
    am = Amendment("am-001", adr_ref="adr/0006", path="witnesses",
                   patch={"active": 9}, rationale="two more honest devices enrolled")
    g.propose(am)
    g.simulate(am)
    g.veto(am, veto_keys=True)
    out = g.execute(am)
    v = g.log.verify()
    return (f"amendment {am.amendment_id}: {am.status}, canon witnesses.active now "
            f"{g.canon['witnesses']['active']}, log {v}, exec row {out['row']['digest'][:16]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.governance.v1 — gate 3.4 executable")
    ap.add_argument("cmd", choices=["demo"])
    ns = ap.parse_args(argv)
    if ns.cmd == "demo":
        print(demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
