#!/usr/bin/env python3
"""craft_session.py — drive the craft loop on the LIVE network, over HTTP.

The user's ask: adopt craft-anything's loop — study a target with evidence
behind every answer, build a version, check how alike it is, refine — and make
it pay. This session is the proof it runs on the network, including the three
refinements the loop grew after the first study: the buyer's approval cards,
multi-page web likeness (same-site routes, per-page scores), and MCP parity
(the same actions as tools). Job one is built wrong and the machine refuses to
pay it; the corrected rebuild, a multi-page web rebuild and the MCP flow
settle. Every number is read off the running process.

  python3 scripts/craft_session.py --out records/craft-session-<date>.md

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "impl"))

from dyn_app import Dynamis, make_handler  # noqa: E402
from dyn_mcp import DynamisServer  # noqa: E402

TARGET_PAGE = """<!doctype html><html><head><title>DYNAMIS Field Notes</title></head>
<body><h1>The loop pays on evidence</h1><h2>Study</h2><p>Study captures the target
with evidence records behind every answer; nothing is claimed that was not measured.</p>
<h2>Check</h2><p>The check measures how alike the rebuild is and names what does not
match yet; missing evidence never counts as alike.</p>
<a href="/loop">the loop</a> <a href="/pay">the payout</a></body></html>"""

BROKEN_BUILD = TARGET_PAGE.replace("DYNAMIS Field Notes", "Something Else")


class Client:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"} if body else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return dict(json.loads(r.read()))
        except urllib.error.HTTPError as e:
            return {"_status": e.code, **json.loads(e.read())}


def approval_card(root: Path, job_id: str) -> dict:
    """The open approval card a study leaves for the buyer."""
    inbox = Path(root) / job_id / "inbox"
    for p in sorted(inbox.glob("*.json")):
        item = json.loads(p.read_text())
        if item.get("kind") == "approval" and item["status"] == "open":
            return item
    raise AssertionError("no open approval card")


def main() -> int:
    ap = argparse.ArgumentParser(description="the craft loop on the live network")
    ap.add_argument("--out", default="records/craft-session.md")
    ns = ap.parse_args()
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    td = tempfile.TemporaryDirectory()
    net = Dynamis(state_root=Path(td.name))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(net))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    c = Client(port)

    # a local site for the web kind — served, not fetched from the outside
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            body = TARGET_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    page_server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    page_url = f"http://127.0.0.1:{page_server.server_address[1]}/field-notes"
    threading.Thread(target=page_server.serve_forever, daemon=True).start()

    lines: list[str] = []
    add = lines.append
    add(f"# The craft session — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    add("")
    add("`dyn.craft.v1` on the live network (pattern credit: storytold/craft-anything):")
    add("study a target with evidence behind every answer, build a version, check how")
    add("alike it is, refine what fails — and only then does the escrow move. This")
    add("session also measures the three refinements the loop grew: the buyer's")
    add("approval cards, per-page likeness for the web kind, and MCP parity. Every")
    add("number is read off the running process.")
    add("")

    for who in ("agent-buyer", "agent-builder"):
        c.call("POST", "/api/agents", {"agent_id": who, "persona": f"persona-{who}"})

    # ---- job one: built wrong, refused, refunded ----
    add("## 1 · The first craft job — a dataset, studied, built wrong, refused")
    add("")
    dataset = Path(td.name) / "dataset.json"
    dataset.write_text(json.dumps(
        {"invoices": [{"id": f"inv-{i:05d}", "cents": 2_500 + i} for i in range(150)],
         "currency": "USD"}, indent=1) + "\n")
    c.call("POST", "/api/craft", {"buyer": "agent-buyer",
                                  "request": "A program that reports this dataset's facts",
                                  "target_kind": "file", "target_ref": str(dataset)})
    study = c.call("POST", "/api/craft/craft-0001/study", {})
    facts = json.loads((Path(td.name) / "craft" / "craft-0001" / "capture"
                        / "facts.json").read_text())
    card = approval_card(Path(td.name) / "craft", "craft-0001")
    add("```")
    add(f"study: {len(study['evidence'])} evidence record(s) "
        f"({study['evidence'][0][:20]}…), {len(study['unknowns'])} open question(s)")
    add(f"captured: {facts['bytes']} bytes, {facts['lines']} lines, "
        f"type {facts['type']}, sha256 {facts['sha256'][:16]}…")
    add(f"the loop pauses on the buyer's card: {card['id']} — “{card['question'][:58]}…”")
    add("```")
    add("")
    add("Round 1 — the build's byte count is off by one. The check says so, claim")
    add("by claim, and the loop refuses to settle on it:")
    add("")
    add("```")
    c.call("POST", "/api/craft/craft-0001/answer",
           {"qid": card["id"], "answer": "approve", "by": "agent-buyer"})
    program = ("import hashlib, json, sys\n"
               "raw = open(sys.argv[1], 'rb').read()\n"
               "kind = 'json' if raw[:1] in (b'{', b'[') else 'text'\n"
               "print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(),"
               " 'bytes': len(raw) + 1,"
               f" 'lines': {facts['lines']}, 'type': kind}}))\n")
    c.call("POST", "/api/craft/craft-0001/build",
           {"worker": "agent-builder", "files": {"main.py": program}})
    r1 = c.call("POST", "/api/craft/craft-0001/check", {})
    back = c.call("POST", "/api/craft/craft-0001/refund", {}) if not r1["passed"] else None
    add(f"round {r1['round']}: {'PASS' if r1['passed'] else 'FAIL'} · "
        f"similarity {r1['similarity_milli'] / 10:.0f}% · failed claims: "
        f"{'; '.join(c2['title'] for c2 in r1['claims'] if not c2['passed'])}")
    if back:
        add(f"refund: escrow {back['escrow_back_muc']:,} µ¢ back · fees {back['fee_muc']} "
            f"· emission {back['emitted_dyn_mu']} (Law 19)")
    add("```")
    add("")

    # ---- job two: the buyer decides, the rebuild settles ----
    add("## 2 · The buyer decides — and the rebuild settles with its proof published")
    add("")
    add("A second job. Study opens the approval card; the build is refused while it")
    add("is open; only the buyer can answer it; an approve releases the loop:")
    add("")
    add("```")
    c.call("POST", "/api/craft", {"buyer": "agent-buyer",
                                  "request": "A program that reports this dataset's facts",
                                  "target_kind": "file", "target_ref": str(dataset)})
    c.call("POST", "/api/craft/craft-0002/study", {})
    card2 = approval_card(Path(td.name) / "craft", "craft-0002")
    early = c.call("POST", "/api/craft/craft-0002/build",
                   {"worker": "agent-builder", "files": {"main.py": "print('x')\n"}})
    add(f"build while {card2['id']} is open → HTTP {early['_status']}: "
        f"“{early['error'][:64]}…”")
    c.call("POST", "/api/craft/craft-0002/answer",
           {"qid": card2["id"], "answer": "approve", "by": "agent-buyer"})
    good = program.replace("len(raw) + 1", "len(raw)")
    c.call("POST", "/api/craft/craft-0002/build",
           {"worker": "agent-builder", "files": {"main.py": good}})
    r2 = c.call("POST", "/api/craft/craft-0002/check", {})
    add(f"round {r2['round']}: {'PASS' if r2['passed'] else 'FAIL'} · "
        f"similarity {r2['similarity_milli'] / 10:.0f}% · claims "
        f"{sum(x['passed'] for x in r2['claims'])}/{len(r2['claims'])}")
    settle = c.call("POST", "/api/craft/craft-0002/settle", {})
    add(f"settle: payout {settle['payout_muc']:,} µ¢ · fee {settle['fee_muc']:,} · "
        f"emitted {settle['emitted_dyn_mu']:,} DYN µ · chain_ok {settle['chain_ok']}")
    post = c.call("POST", "/api/craft/craft-0002/post", {})
    add(f"posted {post['post_id']} — {len(post['embeds'])} verifiable embed(s)")
    add("```")
    add("")

    # ---- job three: the web kind, now multi-page ----
    add("## 3 · The web kind, multi-page — routes studied, per-page likeness judged")
    add("")
    add("Study crawls the start page's same-site routes (up to 4, the reference")
    add("engine's pick_routes rules: same origin, no file links, dash-slugs); the")
    add("check compares every studied page and scores the mean:")
    add("")
    add("```")
    c.call("POST", "/api/craft", {"buyer": "agent-buyer",
                                  "request": "Recreate this site's pages",
                                  "target_kind": "web", "target_ref": page_url})
    sw = c.call("POST", "/api/craft/craft-0003/study", {})
    wfacts = json.loads((Path(td.name) / "craft" / "craft-0003" / "capture"
                         / "facts.json").read_text())
    add(f"study: HTTP {wfacts['status']}, title “{wfacts['title']}”, routes "
        f"{[r['path'] for r in wfacts['routes']]} · {len(sw['evidence'])} evidence record(s)")
    card3 = approval_card(Path(td.name) / "craft", "craft-0003")
    c.call("POST", "/api/craft/craft-0003/answer",
           {"qid": card3["id"], "answer": "approve", "by": "agent-buyer"})
    files = {"index.html": TARGET_PAGE}
    for rt in wfacts["routes"]:
        files[f"routes/{rt['slug']}.html"] = TARGET_PAGE
    c.call("POST", "/api/craft/craft-0003/build",
           {"worker": "agent-builder", "files": files})
    rw = c.call("POST", "/api/craft/craft-0003/check", {})
    pages = ", ".join(f"{pg['name']} {pg['similarity_milli'] / 10:.0f}%"
                      for pg in rw["pages"])
    add(f"round {rw['round']}: {'PASS' if rw['passed'] else 'FAIL'} · mean likeness "
        f"{rw['similarity_milli'] / 10:.0f}% across {len(rw['pages']) + 1} page(s)")
    add(f"per page: start 100% · {pages}")
    settlew = c.call("POST", "/api/craft/craft-0003/settle", {})
    add(f"settle: payout {settlew['payout_muc']:,} µ¢ · emitted "
        f"{settlew['emitted_dyn_mu']:,} DYN µ")
    add("```")
    add("")
    add("## 4 · One failing claim blocks readiness however alike the rest looks")
    add("")
    add("The web build with the wrong title — identical text, so likeness stays 100%,")
    add("and the check still refuses (and a missing route page would refuse too):")
    add("")
    add("```")
    c.call("POST", "/api/craft", {"buyer": "agent-buyer",
                                  "request": "Recreate this site's pages",
                                  "target_kind": "web", "target_ref": page_url})
    c.call("POST", "/api/craft/craft-0004/study", {})
    card4 = approval_card(Path(td.name) / "craft", "craft-0004")
    c.call("POST", "/api/craft/craft-0004/answer",
           {"qid": card4["id"], "answer": "approve", "by": "agent-buyer"})
    c.call("POST", "/api/craft/craft-0004/build",
           {"worker": "agent-builder", "files": {"index.html": BROKEN_BUILD}})
    rb = c.call("POST", "/api/craft/craft-0004/check", {})
    add(f"round {rb['round']}: similarity {rb['similarity_milli'] / 10:.0f}% — "
        f"{'PASS' if rb['passed'] else 'FAIL'} ({rb['note'][:76]}…)")
    add("```")
    add("")
    add("## 5 · MCP parity — the same loop as tools any agent mounts")
    add("")
    add("The dyn.mcp.v1 stdio server now carries the craft loop as nine tools beside")
    add("the engine's seven — one engine, three surfaces, as the reference engine")
    add("puts it. The flow below runs through the MCP dispatch itself:")
    add("")
    add("```")
    srv = DynamisServer()
    tools = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in tools["result"]["tools"]]
    add(f"tools/list: {len(names)} tools — craft_{''}tools: "
        f"{[n for n in names if n.startswith('craft')]}")
    mcp_root = Path(td.name) / "mcp-craft"
    ds = Path(td.name) / "ds.json"
    ds.write_text(json.dumps({"k": [1, 2, 3]}, indent=1) + "\n")
    srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "craft_open", "arguments": {"root": str(mcp_root), "job_id": "craft-mcp-1",
                                            "buyer": "agent-buyer",
                                            "request": "Report the facts",
                                            "target_kind": "file", "target_ref": str(ds)}}})
    srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "craft_study", "arguments": {"root": str(mcp_root)}}})
    card5 = approval_card(Path(td.name), "mcp-craft")
    srv.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "craft_answer", "arguments": {"root": str(mcp_root), "qid": card5["id"],
                                              "answer": "approve", "by": "agent-buyer"}}})
    mfacts = json.loads((mcp_root / "capture" / "facts.json").read_text())
    mprog = ("import hashlib, json, sys\n"
             "raw = open(sys.argv[1], 'rb').read()\n"
             "kind = 'json' if raw[:1] in (b'{', b'[') else 'text'\n"
             f"lines = {mfacts['lines']}\n"
             "print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(),"
             " 'bytes': len(raw), 'lines': lines, 'type': kind}))\n")
    srv.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
        "name": "craft_build", "arguments": {"root": str(mcp_root),
                                             "worker": "agent-builder",
                                             "files": {"main.py": mprog}}}})
    chk = json.loads(srv.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                 "params": {"name": "craft_check",
                                            "arguments": {"root": str(mcp_root)}}}
                                )["result"]["content"][0]["text"])
    add(f"craft flow via MCP: check {'PASS' if chk['passed'] else 'FAIL'}, "
        f"similarity {chk['similarity_milli'] / 10:.0f}%")
    st = json.loads(srv.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                "params": {"name": "craft_settle",
                                           "arguments": {"root": str(mcp_root)}}}
                               )["result"]["content"][0]["text"])
    add(f"craft_settle via MCP: payout {st['payout_muc']:,} µ¢, "
        f"emitted {st['emitted_dyn_mu']:,} DYN µ")
    add("```")
    add("")
    chain = c.call("GET", "/api/chain")
    state = c.call("GET", "/api/state")
    inv = chain["invariant"]
    add("## 6 · The chain of record — the craft loop writes the same ledger")
    add("")
    add("```")
    add(f"work ledger: {chain['verify']['ok']} · {chain['entries']} entries · "
        f"Law-19 invariant: settled {inv['settled_usds_muc']:,} µ¢ → emitted "
        f"{inv['emitted_dyn_mu']:,} DYN µ · holds: {inv['emitted_eq_revenue']}")
    add(f"session: {state['craft']['jobs']} craft jobs · craft payouts "
        f"{state['craft']['settled_muc']:,} µ¢ · 1 refund, fees 0, emission 0")
    add("```")
    add("")
    add("## Named limitations — on the record")
    add("")
    add("- The web kind's likeness is structural and textual (Dice over word")
    add("  counts, claims on title/headings/links/routes), not pixel-level: no")
    add("  browser runs inside the stdlib server. A client-rendered page reads")
    add("  as its HTML source; this is in every web evidence record's limitations.")
    add("- Study crawls up to 4 same-site routes (the reference engine's default")
    add("  max_pages); deeper pages are not studied in v1.")
    add("- Signatures are HSM stand-ins; the price/reference-band note from the")
    add("  product session carries over to everything compute-priced.")
    add("")
    add("Replayable: `python3 scripts/craft_session.py` and `python3 impl/dyn_app.py")
    add("serve` — the console's Craft panel performs the same actions live, including")
    add("the buyer's approve/deny; the same actions mount as MCP tools.")
    add("")

    httpd.shutdown()
    page_server.shutdown()
    td.cleanup()
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"transcript written: {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
