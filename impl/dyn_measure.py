"""dyn_measure — what the craft loop changes, measured over the real paths.

The loop does not make generation smarter; it decides what survives to
the buyer. Workers here are seeded draws over a stated error model —
deterministic, recomputable — but every pipeline step is the real one:
open, study, the approval card, build, the re-executed check, settle or
refund, the ledger, the seals. Three pipelines price the SAME deliveries
from the SAME worker draws:

  naive        — the buyer pays every delivery, verifies nothing
  self-report  — the worker's own claim is the gate (nothing re-executed)
  craft        — open → study → approval → build → check → settle or refund

Money is read from the delivered rows, not asserted by the model: settle
carries payout/fee, refund carries escrow_back. Determinism: pool, draws,
verdicts and every µ¢ are a function of the seed — wall-clock overhead is
the one reported number that is not. The honest scope: this measures the
PROTOCOL's effect (what ships, what it costs, who earns) under a stated
generation-error model; it does not measure model quality — that takes
real agents and is named as the next measurement.
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import random
import time
from pathlib import Path

P_BROKEN = 0.30            # share of builds the worker model ships broken
P_FORGED_OF_BROKEN = 0.50  # share of broken builds that CLAIM "it is correct"
VALUE_USDS = 200           # escrow per task — 200,000,000 µ¢

_PAGES = {
    "docs-loop": """<!doctype html><html><head><title>The Work Loop</title></head>
<body><h1>The work loop</h1><h2>Escrow</h2><p>Money moves on evidence alone.</p>
<h2>Settlement</h2><p>The check harness re-runs the shipped bytes first.</p>
<a href="/loop">the loop</a></body></html>""",
    "docs-money": """<!doctype html><html><head><title>The Money</title></head>
<body><h1>The money</h1><h2>Emission</h2><p>Emitted equals revenue-verified.</p>
<h2>Fees</h2><p>A failed build refunds with zero fees.</p>
<a href="/money">the money</a></body></html>""",
    "docs-posts": """<!doctype html><html><head><title>Posts</title></head>
<body><h1>Posts</h1><h2>Wire</h2><p>Canonical, integers only.</p>
<h2>Embeds</h2><p>The shipped bytes ride inside the post.</p>
<a href="/posts">posts</a></body></html>""",
}


def _dataset(seed: int, idx: int, rows: int) -> dict:
    rng = random.Random(f"{seed}:ds:{idx}")
    return {"name": f"dataset-{idx:03d}", "rows": rows,
            "items": [{"qty": rng.randint(1, 9), "unit_muc": rng.randrange(150, 9_900)}
                      for _ in range(rows)]}


def task_pool(seed: int, n_tasks: int, root: Path) -> list[dict]:
    """Half the pool is file-kind fingerprint reports, half is web-kind
    faithful rebuilds — both drive the craft loop's real check paths."""
    rng = random.Random(f"{seed}:pool")
    tasks = []
    droot = root / "bench-targets"
    droot.mkdir(parents=True, exist_ok=True)
    for i in range(n_tasks):
        if i % 2 == 0:
            data = _dataset(seed, i // 2, rows=rng.randint(20, 60))
            path = droot / f"{data['name']}.json"
            path.write_text(json.dumps(data, indent=1) + "\n")
            tasks.append({"task_id": f"t-{i:03d}", "kind": "file", "ref": str(path),
                          "name": data["name"],
                          "request": f"Report the exact fingerprint of {data['name']}: "
                                     f"sha256, byte size, line count, type — "
                                     f"every field must match byte-for-byte."})
        else:
            key = ("docs-loop", "docs-money", "docs-posts")[rng.randrange(3)]
            path = droot / f"page-{i:03d}.html"
            path.write_text(_PAGES[key])
            tasks.append({"task_id": f"t-{i:03d}", "kind": "web", "ref": str(path),
                          "name": key,
                          "request": f"Rebuild the {key} documentation page faithfully — "
                                     f"same title, same headings, same words, "
                                     f"no injected scripts."})
    return tasks


def worker_draws(seed: int, tasks: list[dict],
                 p_broken: float = P_BROKEN,
                 p_forged: float = P_FORGED_OF_BROKEN) -> list[dict]:
    """The stated error model: which builds ship broken, which broken
    builds claim 'correct'. Workers are two personas so the income
    gradient is a person, not an abstraction."""
    rng = random.Random(f"{seed}:draws")
    draws = []
    for t in tasks:
        broken = rng.random() < p_broken
        variant = None
        forged = False
        if broken:
            variant = ("lines_plus_one", "short_sha", "wrong_type")[
                rng.randrange(3)] if t["kind"] == "file" else (
                "title_swap", "heading_drop", "script_inject")[rng.randrange(3)]
            forged = rng.random() < p_forged
        draws.append({"task_id": t["task_id"], "kind": t["kind"],
                      "worker": "agent-shaky-1" if broken else "agent-honest-1",
                      "broken": broken, "variant": variant, "forged": forged})
    return draws


def build_files(task: dict, draw: dict) -> dict[str, str]:
    """The shipped bytes — correct, or broken in the drawn way."""
    if task["kind"] == "file":
        raw = Path(task["ref"]).read_bytes()
        facts = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                 "lines": raw.count(b"\n"), "type": "json"}
        v = draw["variant"]
        if v == "lines_plus_one":
            facts["lines"] += 1
        elif v == "short_sha":
            facts["sha256"] = facts["sha256"][:16] + "0" * 48
        elif v == "wrong_type":
            facts["type"] = "csv"
        code = (
            "#!/usr/bin/env python3\n"
            "import hashlib, json, sys\n"
            "raw = open(sys.argv[1], 'rb').read()\n"
            "kind = 'json' if raw[:1] in (b'{', b'[') else 'text'\n"
            f"lines = {facts['lines']}\n"
            f"sha = {facts['sha256']!r}\n"
            f"typed = {facts['type']!r}\n"
            "print(json.dumps({'sha256': sha, 'bytes': len(raw),\n"
            "                  'lines': lines, 'type': typed}))\n")
        return {"main.py": code}
    html = Path(task["ref"]).read_text()
    v = draw["variant"]
    if v == "title_swap":
        html = html.replace("<title>", "<title> Totally Unrelated —", 1)
    elif v == "heading_drop":
        html = html.replace("<h2>", "<p>", 1)
    elif v == "script_inject":
        html = html.replace("</body>",
                            '<script>document.title="hacked";</script></body>')
    return {"index.html": html}


class _PoolHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the pool's pages so the web-kind loop really fetches over
    HTTP — the same urllib path a live target rides. Any other path the
    study follows (the pages' relative links) gets a real minimal page:
    a link that 404s would enter the capture as unknowns, and unknowns
    block settlement by design — missing evidence never counts as alike."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        p = Path(self.directory) / self.path.lstrip("/").split("?")[0]
        if p.is_file():
            super().do_GET()
            return
        body = ("<!doctype html><html><head><title>linked</title></head>"
                f"<body><h1>{self.path}</h1><p>linked page, served by the pool"
                "</p></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _QuietServer(http.server.ThreadingHTTPServer):
    def __init__(self, addr, directory):
        handler = functools.partial(_PoolHandler, directory=str(directory))
        super().__init__(addr, handler)


def run_craft(app, pool: list[dict], draws: list[dict]) -> tuple[list[dict], int]:
    """The real loop, one honest pass per task (repair rate 0 — stated).
    Returns per-job rows and total wall-clock."""
    escrow_muc = VALUE_USDS * 1_000_000
    rows = []
    t_all = time.perf_counter()
    for task, draw in zip(pool, draws):
        t0 = time.perf_counter()
        app.open_craft(buyer="agent-buyer", request=task["request"],
                       target_kind=task["kind"], target_ref=task.get("url") or task["ref"],
                       value_usds=VALUE_USDS)
        jid = f"craft-{app._craft_seq:04d}"
        app.craft_study(jid)
        card = next(p for p in (app.state_root / "craft" / jid / "inbox").glob("*.json")
                    if json.loads(p.read_text())["kind"] == "approval")
        app.craft_answer(jid, card.stem, "approve", "agent-buyer")
        files = build_files(task, draw)
        if task["kind"] == "web":
            # a faithful rebuild includes every studied route, fetched from
            # the same origin — the variant mutates the start page only
            import urllib.request
            facts = json.loads((app.state_root / "craft" / jid /
                                "capture" / "facts.json").read_text())
            origin = task["url"].rsplit("/", 1)[0]
            for rt in facts.get("routes", []):
                with urllib.request.urlopen(origin + rt["path"], timeout=10) as r:
                    files[f"routes/{rt['slug']}.html"] = r.read().decode()
        app.craft_build(jid, draw["worker"], files)
        check = app.craft_check(jid)
        passed = bool(check["passed"])
        if passed:
            out = app.craft_settle(jid)
            # the buyer's cost is the whole escrow that moved — payout + fee
            verdict = out["verdict"]
            paid, back = out["payout_muc"] + out["fee_muc"], 0
        else:
            app.craft_refund(jid)
            verdict, paid, back = "refunded", 0, escrow_muc
        rows.append({"task_id": task["task_id"], "job_id": jid,
                     "broken": draw["broken"], "forged": draw["forged"],
                     "shipped": passed,  # a failed check never reaches the buyer
                     "check_passed": passed, "verdict": verdict,
                     "paid_muc": paid, "escrow_back_muc": back,
                     "ms": int((time.perf_counter() - t0) * 1000)})
    return rows, int((time.perf_counter() - t_all) * 1000)


def run_baseline(pool: list[dict], draws: list[dict]) -> dict[str, list[dict]]:
    """The same deliveries priced without verification: naive pays every
    delivery; self-report trusts the worker's claim — a claim gates
    nothing, so broken ships there too, and forged claims go unnoticed."""
    escrow_muc = VALUE_USDS * 1_000_000
    out = {}
    for name in ("naive", "self_report"):
        rows = []
        for task, draw in zip(pool, draws):
            rows.append({"task_id": task["task_id"], "broken": draw["broken"],
                         "shipped": True,  # no verification, everything ships
                         "forged_slipped": draw["forged"] and name == "self_report",
                         "paid_muc": escrow_muc, "escrow_back_muc": 0})
        out[name] = rows
    return out


def summarize(pool, draws, craft_rows, craft_ms, baseline) -> dict:
    escrow_muc = VALUE_USDS * 1_000_000
    n = len(pool)
    broken_total = sum(1 for d in draws if d["broken"])
    forged_total = sum(1 for d in draws if d["forged"])

    def pipe(rows, *, is_craft):
        shipped = sum(1 for r in rows if r["broken"] and r["shipped"])
        paid = sum(r["paid_muc"] for r in rows)
        back = sum(r["escrow_back_muc"] for r in rows)
        if is_craft:
            caught = sum(1 for r in rows if r["forged"] and not r["check_passed"])
        else:
            caught = 0  # nothing re-executes; claims gate nothing
        working = sum(1 for r in rows if r["shipped"] and not r["broken"])
        return {"tasks": len(rows), "shipped_broken": shipped,
                "working_delivered": working,
                "buyer_paid_muc": paid, "escrow_back_muc": back,
                "cost_per_working_muc": paid // max(1, working),
                "forged_caught": caught}

    craft = pipe(craft_rows, is_craft=True)
    naive = pipe(baseline["naive"], is_craft=False)
    self_rep = pipe(baseline["self_report"], is_craft=False)
    for r in craft_rows:  # forged == claimed correct; the check is the gate
        if r["forged"] and r["check_passed"]:
            raise AssertionError("a forged claim passed the check — the harness broke")
    honest_paid = sum(r["paid_muc"] for r in craft_rows if not r["broken"])
    shaky_paid = sum(r["paid_muc"] for r in craft_rows if r["broken"])
    for name in ("naive", "self_report"):  # same fee basis everywhere
        for r in baseline[name]:
            r["paid_muc"] = escrow_muc  # delivery price, no verification
    # money conservation, read from the delivered rows themselves
    assert naive["buyer_paid_muc"] == n * escrow_muc
    assert craft["buyer_paid_muc"] + craft["escrow_back_muc"] == n * escrow_muc
    assert craft["shipped_broken"] == 0, "craft shipped a broken build"
    assert naive["shipped_broken"] == broken_total
    assert craft["forged_caught"] == forged_total
    assert self_rep["shipped_broken"] == broken_total
    return {
        "pool": {"tasks": n, "file": sum(1 for t in pool if t["kind"] == "file"),
                 "web": sum(1 for t in pool if t["kind"] == "web"),
                 "escrow_usds": VALUE_USDS, "pool_value_usds": n * VALUE_USDS},
        "worker_model": {"p_broken": P_BROKEN,
                         "p_forged_of_broken": P_FORGED_OF_BROKEN,
                         "broken_draws": broken_total,
                         "forged_draws": forged_total,
                         "correct_draws": n - broken_total},
        "pipelines": {"naive": naive, "self_report": self_rep, "craft": craft},
        "worker_income_muc": {"agent-honest-1": honest_paid,
                              "agent-shaky-1": shaky_paid,
                              "gradient": "broken builds earn zero; correctness is the only income"},
        "overhead": {"ms_per_job_avg": round(sum(r["ms"] for r in craft_rows) / n, 1),
                     "ms_total": craft_ms},
    }


def run_bench(*, seed: int = 20261106, n_tasks: int = 60, root: Path | None = None,
              app=None) -> dict:
    """The whole measurement. The caller may pass its own app (tests reuse
    one state root); default builds a fresh Dynamis with the personas.
    The pool's pages are served over a local HTTP server so the web-kind
    study rides the real fetch path."""
    import tempfile
    import threading
    td = None
    if root is None:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
    if app is None:
        from dyn_app import Dynamis
        app = Dynamis(state_root=root)
        for who in ("agent-buyer", "agent-honest-1", "agent-shaky-1"):
            app.join(who, f"persona-{who}")
    pool = task_pool(seed, n_tasks, root)
    srv = _QuietServer(("127.0.0.1", 0), root / "bench-targets")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    for task in pool:
        if task["kind"] == "web":
            task["url"] = f"{base}/{Path(task['ref']).name}"
    try:
        draws = worker_draws(seed, pool)
        craft_rows, craft_ms = run_craft(app, pool, draws)
        baseline = run_baseline(pool, draws)
        metrics = summarize(pool, draws, craft_rows, craft_ms, baseline)
    finally:
        srv.shutdown()
    metrics["run"] = {"seed": seed, "n_tasks": n_tasks,
                      "entries": len(app.ledger.entries),
                      "seals": len(app.checkpoints),
                      "audit_ok": app.craft_audit()["ok"]}
    if td is not None:
        td.cleanup()
    return metrics
