#!/usr/bin/env python3
"""dyn.mcp.v1 — the engine behind tool calls: a minimal MCP server.

docs/13 §3 promised "each engine subcommand is one tool call"; this is that
door. It speaks the Model Context Protocol (JSON-RPC 2.0, newline-delimited
JSON over stdio) and maps the dyn.engine.v1 loop onto MCP tools — no SDK, no
network, stdlib only (ADR-0007). Any MCP-capable agent mounts it:

    {
      "mcpServers": {
        "dynamis": { "command": "python3", "args": ["impl/dyn_mcp.py"] }
      }
    }

Tools (state lives in the job folders on disk, so calls are restart-safe):

  dyn_job_new   open a job folder — escrow priced by the ladder at open (Law 9)
  dyn_work      submit an artifact file into the job folder
  dyn_check     run the evidence harness; records land in <root>/evidence/
  dyn_settle    pay from escrow — fail-closed on the PASS evidence on disk
  dyn_refund    the fail path — escrow returns, zero fees, zero emission
  dyn_post      publish the settled work as a hash-bound dyn.post.v1 object
  dyn_status    read the job log: status, class, escrow, history tail

An engine rule violation (e.g. settling an open job) is a tool *result* with
isError=true — the loop refusing to skip steps is information, not a crash.

  python3 dyn_mcp.py            # serve on stdio
  echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 dyn_mcp.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_craft import CraftJob, CraftError, MAX_ROUTES  # noqa: E402
from dyn_engine import EngineError, WorkLoop  # noqa: E402
from dyn_ledger import WorkLedger as CraftLedger  # noqa: E402
from dynamis_core import usds  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "dynamis", "version": "1.0.0"}
CURRENCIES = ("USD", "EUR")
BUYERS = 20


# --------------------------------------------------------------------------
# tool handlers — each is one engine step, nothing more
# --------------------------------------------------------------------------
def h_job_new(a: dict) -> dict:
    day = int(a.get("day", 1))
    loop = WorkLoop(a["root"])
    job = loop.job_new(
        job_id=a["job_id"], entity_id=a.get("entity_id", "ent-001"),
        revenue_ref=a.get("revenue_ref", "env-ops-001"),
        value_muc=usds(int(a["value_usds"])),
        deadline_day=int(a.get("deadline_day", day + 7)),
        seed=int(a.get("seed", 1000)), count=int(a.get("count", 250)),
        currencies=CURRENCIES, buyer_count=BUYERS, day=day)
    return {"job_id": job["job_id"], "status": "open",
            "verification_class": job["verification_class"],
            "escrow_usds_muc": job["escrow_usds_muc"],
            "input_sha256": job["spec"]["input_sha256"]}


def h_work(a: dict) -> dict:
    return WorkLoop(a["root"]).work(a["artifact"])


def h_check(a: dict) -> dict:
    return WorkLoop(a["root"]).check(day=int(a.get("day", 1)))


def h_settle(a: dict) -> dict:
    worker = a.get("worker_id", "agent-honest-1")
    return WorkLoop(a["root"]).settle(
        day=int(a.get("day", 10)), worker_id=worker,
        persona=f"{worker}.persona", keyref=f"hsm:kr-{worker}")


def h_refund(a: dict) -> dict:
    return WorkLoop(a["root"]).refund(
        day=int(a.get("day", 10)), worker_id=a.get("worker_id", "agent-honest-1"))


def h_post(a: dict) -> dict:
    wire = WorkLoop(a["root"]).post(post_id=a["post_id"],
                                    day=int(a.get("day", 10)))
    return {"post_id": wire["post_id"], "embeds": len(wire["embeds"]),
            "wire": "post/post.wire.json"}


def h_status(a: dict) -> dict:
    loop = WorkLoop(a["root"])
    if not loop.log:
        return {"root": str(a["root"]), "status": "not_a_job_folder"}
    j = loop.log["job"]
    return {"job_id": j["job_id"], "status": loop.log["status"],
            "verification_class": j["verification_class"],
            "escrow_usds_muc": j["escrow_usds_muc"],
            "evidence_records": len(loop.log.get("evidence", [])),
            "history": [h["kind"] for h in loop.log.get("history", [])]}


# ---- the craft loop (dyn.craft.v1): same actions as the CLI and the app ----
def _craft_ledger() -> CraftLedger:
    return CraftLedger()


def h_craft_open(a: dict) -> dict:
    m = CraftJob(a["root"]).open(
        job_id=a["job_id"], buyer=a["buyer"], request=a["request"],
        target_kind=a["target_kind"], target_ref=a["target_ref"],
        value_usds=int(a.get("value_usds", 500)),
        max_rounds=int(a.get("max_rounds", 6)),
        good_enough=float(a.get("good_enough", 90.0)),
        ledger=_craft_ledger(), day=int(a.get("day", 1)))
    return {"job_id": m["job_id"], "status": m["status"],
            "escrow_usds_muc": m["escrow_usds_muc"],
            "rounds": m["rounds"], "good_enough": m["good_enough"]}


def h_craft_study(a: dict) -> dict:
    return CraftJob(a["root"]).study(ledger=_craft_ledger(), day=int(a.get("day", 1)))


def h_craft_build(a: dict) -> dict:
    return CraftJob(a["root"]).build(
        worker=a["worker"], files=a["files"],
        ledger=_craft_ledger(), day=int(a.get("day", 1)))


def h_craft_check(a: dict) -> dict:
    return CraftJob(a["root"]).check(ledger=_craft_ledger(), day=int(a.get("day", 1)))


def h_craft_settle(a: dict) -> dict:
    worker = a.get("worker", "agent-worker")
    return CraftJob(a["root"]).settle(
        ledger=_craft_ledger(), day=int(a.get("day", 1)),
        persona=a.get("persona", f"{worker}.persona"),
        keyref=a.get("keyref", f"hsm:kr-{worker}"))


def h_craft_verify(a: dict) -> dict:
    from dyn_witness import craft_evidence_digest
    from dyn_witness import craft_verify as run_game
    job = CraftJob(a["root"])
    m = job.manifest
    if not m.get("checks"):
        raise ValueError("no check on the record to verify")
    out = run_game(job.root, day=int(a.get("day", 1)),
                   delivered_digest=craft_evidence_digest(m["checks"][-1]))
    out["job_id"] = m["job_id"]
    out["status"] = m["status"]
    return out


def h_craft_refund(a: dict) -> dict:
    return CraftJob(a["root"]).refund(ledger=_craft_ledger(), day=int(a.get("day", 1)))


def h_craft_post(a: dict) -> dict:
    wire = CraftJob(a["root"]).post(day=int(a.get("day", 1)))
    return {"post_id": wire["post_id"], "embeds": len(wire["embeds"])}


def h_craft_answer(a: dict) -> dict:
    return CraftJob(a["root"]).answer(
        a["qid"], a["answer"], by=a.get("by"),
        ledger=_craft_ledger(), day=int(a.get("day", 1)))


def h_craft_view(a: dict) -> dict:
    return dict(CraftJob(a["root"]).manifest)


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_ROOT = {"root": {"type": "string", "description": "job folder path"}}
_TOOLS_SPEC: list[dict] = [
    ("dyn_job_new", "Open a job folder: escrow in USDS, floor verification class priced by Law 9, deterministic target inputs pinned by sha256.",
     _schema({"root": _ROOT["root"], "job_id": {"type": "string"},
              "value_usds": {"type": "integer", "description": "escrow in whole USDS"},
              "count": {"type": "integer", "description": "invoices in the batch"},
              "seed": {"type": "integer"}, "day": {"type": "integer"}},
             ["root", "job_id", "value_usds"]), h_job_new),
    ("dyn_work", "Submit an artifact file (path) into the job folder. Its sha256 enters your claim.",
     _schema({"root": _ROOT["root"], "artifact": {"type": "string", "description": "path to the artifact file"}},
             ["root", "artifact"]), h_work),
    ("dyn_check", "Run the evidence harness on the shipped bytes: artifact_runs, contract_shape, totals_match_ground_truth, bounded_runtime. Refines reset the evidence index — only the latest run vouches.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}}, ["root"]), h_check),
    ("dyn_settle", "Settle from escrow — re-reads the evidence from disk first; all-PASS or no payout path (Law 19). Terminal.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}, "worker_id": {"type": "string"}},
             ["root"]), h_settle),
    ("dyn_refund", "The fail path after a FAIL check: escrow returns to the budget, zero fees, zero emission. Terminal.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}, "worker_id": {"type": "string"}},
             ["root"]), h_refund),
    ("dyn_post", "Publish the settled work as a dyn.post.v1 wire object with the artifact as a hash-bound embed — your verifiable portfolio entry.",
     _schema({"root": _ROOT["root"], "post_id": {"type": "string"}, "day": {"type": "integer"}},
             ["root", "post_id"]), h_post),
    ("dyn_status", "Read the job log: status, verification class, escrow, evidence count, history.",
     _schema({"root": _ROOT["root"]}, ["root"]), h_status),
    # ---- dyn.craft.v1: the craft loop, the same actions the CLI and the app expose ----
    ("craft_open", "Open a craft job on a target (kind web or file) with the buyer's request in their words; escrow named in the manifest.",
     _schema({"root": _ROOT["root"], "job_id": {"type": "string"},
              "buyer": {"type": "string"}, "request": {"type": "string"},
              "target_kind": {"type": "string", "enum": ["web", "file"]},
              "target_ref": {"type": "string"},
              "value_usds": {"type": "integer"}, "max_rounds": {"type": "integer"},
              "good_enough": {"type": "integer"}, "day": {"type": "integer"}},
             ["root", "job_id", "buyer", "request", "target_kind", "target_ref"]),
     h_craft_open),
    ("craft_study", "Capture the target: the page or file facts, same-site routes (up to 4), evidence records behind every answer; opens the buyer's approval card.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}}, ["root"]), h_craft_study),
    ("craft_build", "Submit the build (files: name -> content). Refused while the buyer's approval card is open.",
     _schema({"root": _ROOT["root"], "worker": {"type": "string"},
              "files": {"type": "object", "additionalProperties": {"type": "string"}},
              "day": {"type": "integer"}}, ["root", "worker", "files"]), h_craft_build),
    ("craft_check", "Measure how alike the build is: Dice likeness, claims judged one by one, per-page likeness for web routes; unknowns block.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}}, ["root"]), h_craft_check),
    ("craft_settle", "Settle the escrow on a passing check with every claim holding and no unknowns. Fail-closed.",
     _schema({"root": _ROOT["root"], "worker": {"type": "string"},
              "persona": {"type": "string"}, "keyref": {"type": "string"},
              "day": {"type": "integer"}}, ["root"]), h_craft_settle),
    ("craft_verify", "Re-run the verification game read-only: fresh re-execution must reproduce the submitted check and the facts must match the buyer's approval pin. No money moves.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}}, ["root"]), h_craft_verify),
    ("craft_refund", "The fail path: a FAIL round or a buyer's deny — escrow returns, zero fees, zero emission.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}}, ["root"]), h_craft_refund),
    ("craft_post", "Publish the settled proof as a dyn.post.v1 wire object carrying the shipped bytes.",
     _schema({"root": _ROOT["root"], "day": {"type": "integer"}}, ["root"]), h_craft_post),
    ("craft_answer", "Answer an inbox card. Approval cards: the buyer only, approve or deny — deny ends the loop for a refund.",
     _schema({"root": _ROOT["root"], "qid": {"type": "string"},
              "answer": {"type": "string"}, "by": {"type": "string"},
              "day": {"type": "integer"}}, ["root", "qid", "answer"]), h_craft_answer),
    ("craft_view", "Read the craft.json manifest: request, target, status, rounds, checks history, post.",
     _schema({"root": _ROOT["root"]}, ["root"]), h_craft_view),
]
TOOLS = {name: {"name": name, "description": desc, "inputSchema": schema,
                "handler": handler}
         for name, desc, schema, handler in _TOOLS_SPEC}


class DynamisServer:
    """JSON-RPC dispatch, testable without a process: handle() in, reply out."""

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        if "id" not in msg:                      # notification — no reply
            return None
        mid = msg["id"]
        try:
            if method == "initialize":
                result = {"protocolVersion": PROTOCOL_VERSION,
                          "capabilities": {"tools": {}},
                          "serverInfo": SERVER_INFO}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{k: t[k] for k in
                                     ("name", "description", "inputSchema")}
                                    for t in TOOLS.values()]}
            elif method == "tools/call":
                result = self._call(msg.get("params", {}))
            else:
                return self._err(mid, -32601, f"method not found: {method}")
        except EngineError as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except CraftError as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except (KeyError, TypeError, ValueError) as e:
            result = {"content": [{"type": "text", "text": f"bad arguments: {e}"}],
                      "isError": True}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _call(self, params: dict) -> dict:
        name = params.get("name", "")
        if name not in TOOLS:
            raise ValueError(f"unknown tool: {name}")
        out = TOOLS[name]["handler"](params.get("arguments", {}))
        return {"content": [{"type": "text", "text": json.dumps(out, sort_keys=True)}],
                "isError": False}

    @staticmethod
    def _err(mid, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": code, "message": message}}


def main() -> int:
    srv = DynamisServer()
    for line in sys.stdin:                       # newline-delimited JSON-RPC
        line = line.strip()
        if not line:
            continue
        reply = srv.handle(json.loads(line))
        if reply is not None:
            sys.stdout.write(json.dumps(reply, sort_keys=True) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
