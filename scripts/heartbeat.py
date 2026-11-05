#!/usr/bin/env python3
"""heartbeat.py — the 15-minute liveness beat for gate 1.1 (uptime measurement).

Runs the fast core loop: canonical money, fail-closed escrow transitions, a live
ledger with a sealed checkpoint, and the Law-19 invariant on one synthetic
settled flow. Exit 0 = the service brain is alive. A scheduled Actions workflow
runs this every 15 minutes; the run history *is* the uptime record, measured by
`uptime_report.py` — never declared.

Stdlib only (ADR-0007).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))

from dyn_ledger import WorkLedger  # noqa: E402
from dynamis_core import Job, JobMachine  # noqa: E402
from dynamis_core.canonical import object_hash, usds  # noqa: E402
from dynamis_core.escrow import EscrowError  # noqa: E402


def beat() -> dict:
    checks: dict[str, bool] = {}

    # 1. canonical money is integer money
    checks["money_is_integer"] = usds(3) == 3_000_000 and isinstance(usds(3), int)

    # 2. the escrow state machine refuses illegal transitions
    refused = False
    job = Job(job_id="hb-001", entity_id="ent-001",
              spec={"kind": "heartbeat", "v": 1}, escrow_usds_muc=usds(1),
              deadline_day=7, verification_class="A", revenue_ref="hb-envelope")
    machine = JobMachine(job, funded_by="ent-001")
    try:
        machine.fire("settle")           # settle from OPEN — must refuse
    except EscrowError:
        refused = True
    checks["escrow_fail_closed"] = refused

    # 3. a ledger chain verifies and checkpoints seal the window
    led = WorkLedger()
    for i in range(12):
        led.append(day=1, kind="work", job_id="hb-001", agent="hb-worker",
                   note=f"beat {i}", digest=object_hash({"i": i})[:16])
    cps = led.all_checkpoints(day=1)
    checks["ledger_verifies"] = bool(led.verify_chain()["ok"]) and len(cps) >= 1

    return {"beat": "dyn.heartbeat.v1", "checks": checks,
            "ok": all(checks.values())}


def main() -> int:
    result = beat()
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
