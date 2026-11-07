#!/usr/bin/env python3
"""dyn.live.v1 — real agents against the real harness.

The benchmark priced seeded workers; this layer puts a live model in the
worker's seat. The same pool builder, the same loop (open → study →
approval → build → re-executed check → settle or full refund), the same
sandboxed check with its probes — only the delivery changes: instead of
drawn variants, a real agent reads the buyer's request and the target and
writes the files.

What the agent sees is what a worker legitimately sees: the request, the
target itself, and the protocol's stated conventions (the approval card
settles exactly these). No facts, no check, no probes. What the record
keeps is what the economy keeps: which builds shipped, which claims
failed, what the escrow paid and returned — plus the reply's hash; the
full replies ride in the job folders like any delivery.

Scope, stated: this measures protocol effect on live builders on one
day, with one model behind one CLI — not model quality, not a
leaderboard. The seeded record remains the deterministic baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import dyn_measure as dm

PROMPT_TIMEOUT_S = 180
WORKER = "agent-live-llm"


def brief_for(task: dict) -> str:
    """The worker's legitimate view: request + target + stated conventions."""
    if task["kind"] == "file":
        return (
            "You are a worker in an escrowed freelance economy.\n"
            "The buyer's request:\n" + task["request"] + "\n\n"
            "The target file, verbatim, between the markers:\n<<<TARGET\n"
            + Path(task["ref"]).read_text() + "\nTARGET>>>\n\n"
            "Deliver one Python 3 program named main.py that, given the "
            "target's path as sys.argv[1], prints one line of JSON with "
            "keys sha256, bytes, lines, type, defined as: sha256 — the hex "
            "digest of the file's bytes; bytes — the byte count; lines — "
            "the count of newline bytes, plus 1 if the file does not end "
            "with a newline (0 for an empty file); type — \"json\" if the "
            "first byte is { or [, else \"text\" when every byte among the "
            "first 512 is tab, newline, carriage return, form feed or "
            "printable, else \"binary\". The program must compute from the "
            "file it is given — a memorized answer fails on unseen inputs. "
            "Reply with the file content only, in one fenced code block.")
    return (
        "You are a worker in an escrowed freelance economy.\n"
        "The buyer's request:\n" + task["request"] + "\n\n"
        "The target page, verbatim, between the markers:\n<<<TARGET\n"
        + Path(task["ref"]).read_text() + "\nTARGET>>>\n\n"
        "Deliver one file named index.html — a faithful rebuild of that "
        "page: same title, same headings, the same visible words, the "
        "same links, and no scripts the original doesn't have. Reply with "
        "the file content only, in one fenced code block.")


def fenced(text: str) -> str:
    """The code block inside an agent reply — or the whole reply."""
    if "```" in text:
        parts = text.split("```")
        body = parts[1] if len(parts) > 1 else parts[0]
        lines = body.splitlines()
        if lines and lines[0].strip() and " " not in lines[0].strip()[:12]:
            lines = lines[1:]                     # a language tag line
        return "\n".join(lines).strip() + "\n"
    return text.strip() + "\n"


def llm_agent(task: dict, *, retries: int = 3,
              backoff_s: tuple[int, ...] = (30, 60, 90),
              pace_s: int = 10) -> tuple[dict[str, str], dict]:
    """One z-ai chat call per task, paced, with backoff for a rate-limited
    day. A call that never lands returns empty files — the check fails
    them, the escrow refunds, and the row keeps the error."""
    brief = brief_for(task)
    meta = {"model": "unknown", "reply_sha256": "", "error": ""}
    content = ""
    with tempfile_dir() as td:
        out = Path(td) / "reply.json"
        for attempt in range(retries + 1):
            try:
                subprocess.run(["z-ai", "chat", "-p", brief,
                                "--output", str(out)],
                               capture_output=True, text=True,
                               timeout=PROMPT_TIMEOUT_S, check=True)
                reply = json.loads(out.read_text())
                content = reply["choices"][0]["message"]["content"]
                meta = {"model": reply.get("model", "unknown"),
                        "reply_sha256": hashlib.sha256(
                            content.encode()).hexdigest(), "error": ""}
                break
            except (subprocess.SubprocessError, json.JSONDecodeError,
                    KeyError, OSError) as exc:
                meta = {"model": "unknown", "reply_sha256": "",
                        "error": str(exc)[:120]}
                if attempt < retries:
                    time.sleep(backoff_s[min(attempt, len(backoff_s) - 1)])
    time.sleep(pace_s)
    name = "main.py" if task["kind"] == "file" else "index.html"
    return ({name: fenced(content)} if content.strip() else {}), meta


def run_live(app, pool: list[dict], agent=llm_agent,
             worker: str = WORKER) -> tuple[list[dict], int]:
    """The real loop with a live builder — one pass per task, repair 0."""
    escrow_muc = dm.VALUE_USDS * 1_000_000
    rows = []
    t_all = time.perf_counter()
    for task in pool:
        t0 = time.perf_counter()
        app.open_craft(buyer="agent-buyer", request=task["request"],
                       target_kind=task["kind"],
                       target_ref=task.get("url") or task["ref"],
                       value_usds=dm.VALUE_USDS)
        jid = f"craft-{app._craft_seq:04d}"
        app.craft_study(jid)
        card = next(p for p in (app.state_root / "craft" / jid / "inbox").glob("*.json")
                    if json.loads(p.read_text())["kind"] == "approval")
        app.craft_answer(jid, card.stem, "approve", "agent-buyer")
        files, meta = agent(task)
        if not files:
            # the reference engine's #736: an empty build claims nothing —
            # the escrow answers with a full refund, the row keeps why
            app.craft_refund(jid)
            rows.append({"task_id": task["task_id"], "job_id": jid,
                         "kind": task["kind"], "shipped": False,
                         "similarity": None,
                         "failed_claims": ["the build wrote nothing — no delivery to check"],
                         "verdict": "refunded", "paid_muc": 0,
                         "escrow_back_muc": escrow_muc,
                         "model": meta.get("model", ""),
                         "reply_sha256": meta.get("reply_sha256", ""),
                         "agent_error": meta.get("error", "empty delivery"),
                         "ms": int((time.perf_counter() - t0) * 1000)})
            print(f"live {task['task_id']} {task['kind']} refunded "
                  "(empty delivery)", flush=True)
            continue
        if task["kind"] == "web":
            # every studied route rides from the same origin, exactly as
            # the seeded worker built — the live agent builds the start page
            facts = json.loads((app.state_root / "craft" / jid /
                                "capture" / "facts.json").read_text())
            origin = task["url"].rsplit("/", 1)[0]
            for rt in facts.get("routes", []):
                with urllib.request.urlopen(origin + rt["path"],
                                            timeout=10) as r:
                    files[f"routes/{rt['slug']}.html"] = r.read().decode()
        app.craft_build(jid, worker, files)
        check = app.craft_check(jid)
        passed = bool(check["passed"])
        if passed:
            out = app.craft_settle(jid)
            verdict, paid, back = out["verdict"], out["payout_muc"], 0
        else:
            app.craft_refund(jid)
            verdict, paid, back = "refunded", 0, escrow_muc
        rows.append({"task_id": task["task_id"], "job_id": jid,
                     "kind": task["kind"], "shipped": passed,
                     "similarity": check.get("similarity_milli"),
                     "failed_claims": [c["title"] for c in check.get("claims", [])
                                       if not c["passed"]],
                     "verdict": verdict, "paid_muc": paid,
                     "escrow_back_muc": back, "model": meta.get("model", ""),
                     "reply_sha256": meta.get("reply_sha256", ""),
                     "agent_error": meta.get("error", ""),
                     "ms": int((time.perf_counter() - t0) * 1000)})
        print(f"live {task['task_id']} {task['kind']} "
              f"{'SHIPPED' if passed else 'refunded'} "
              f"({rows[-1]['ms']} ms)", flush=True)
    return rows, int((time.perf_counter() - t_all) * 1000)


def summarize(rows: list[dict], wall_ms: int) -> dict:
    """What the economy saw: shipments, refunds, faults, wall-clock."""
    shipped = [r for r in rows if r["shipped"]]
    faults: dict[str, int] = {}
    for r in rows:
        for t in r["failed_claims"]:
            faults[t] = faults.get(t, 0) + 1
    return {"n_tasks": len(rows),
            "shipped": len(shipped),
            "refunded": len(rows) - len(shipped),
            "paid_muc": sum(r["paid_muc"] for r in rows),
            "escrow_back_muc": sum(r["escrow_back_muc"] for r in rows),
            "avg_similarity_milli": (round(sum(r["similarity"] or 0
                                               for r in rows) / len(rows))
                                     if rows else 0),
            "faults": dict(sorted(faults.items(), key=lambda kv: -kv[1])),
            "wall_ms": wall_ms}


def tempfile_dir():
    import tempfile
    return tempfile.TemporaryDirectory()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--out", default="records/live-agents.json")
    ap.add_argument("--state", default=None,
                    help="persistent state root — the job folders are the "
                         "evidence of what the agent delivered; default "
                         "rides next to the record")
    args = ap.parse_args()
    import tempfile
    import threading
    from dyn_app import Dynamis
    td = None
    if args.state:
        root = Path(args.state)
        root.mkdir(parents=True, exist_ok=True)
    else:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
    try:
        app = Dynamis(state_root=root / "state")
        for who in ("agent-buyer", WORKER):
            app.join(who, f"persona-{who}")
        pool = dm.task_pool(args.seed, args.tasks, root)
        srv = dm._QuietServer(("127.0.0.1", 0), root / "bench-targets")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        for task in pool:
            if task["kind"] == "web":
                task["url"] = f"{base}/{Path(task['ref']).name}"
        try:
            rows, wall_ms = run_live(app, pool)
        finally:
            srv.shutdown()
        record = {"live": summarize(rows, wall_ms), "rows": rows,
                  "note": "paid_muc is the worker's income (payout only); "
                          "the buyer's cost is payout + fee",
                  "run": {"seed": args.seed, "n_tasks": args.tasks,
                          "worker": WORKER, "agent": "z-ai chat",
                          "state": str(root / "state"),
                          "entries": len(app.ledger.entries),
                          "seals": len(app.checkpoints),
                          "audit_ok": app.craft_audit()["ok"]}}
        Path(args.out).write_text(json.dumps(record, indent=1) + "\n")
        print(json.dumps(record["live"], indent=1))
    finally:
        if td is not None:
            td.cleanup()


if __name__ == "__main__":
    main()
