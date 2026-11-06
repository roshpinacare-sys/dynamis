#!/usr/bin/env python3
"""dyn.console.v1 — the read-only regulator console (gate 3.3's executable half).

Gate 3.3 wants the "consolidated read-only regulator view live in giant@:3000".
The live half needs the persistent host (gate 1.1); the console itself is code,
so it exists here: an HTTP surface over the fleet's consolidated view that
cannot write — not by policy, by construction:

  - GET routes only: /health, /view.json, / — every other method answers 405;
    there is no write route to reach.
  - The books' journal digests are captured once at startup and re-asserted on
    every request; a serving layer that mutated a source book answers 500 and
    names itself. This is dyn_fleet's read-only proof, held continuously.
  - What it serves is exactly dyn.fleet.v1's consolidated_view — the rollup
    digest travels with the response, so a regulator verifies the console
    against the fleet, not against prose.

  python3 dyn_console.py serve --port 3000 --demo      # the measured fleet
  python3 dyn_console.py serve --port 3000 --entities ent-001 ent-002 ent-003

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_entities import instantiate  # noqa: E402
from dyn_fleet import book_revenue_flow, consolidated_view  # noqa: E402
from dynamis_core.canonical import usds  # noqa: E402

CONSOLE = "dyn.console.v1"


class ConsoleError(Exception):
    pass


def demo_fleet(n: int = 3) -> list:
    """The measured demo fleet — the same numbers dyn_fleet's view prints."""
    ents = [instantiate(f"ent-{i + 1:03d}", day=1) for i in range(n)]
    for i, ent in enumerate(ents):
        book_revenue_flow(ent, invoice_id=f"{ent.entity_id}-inv-f1",
                          customer=f"client-{i + 1}",
                          value_muc=usds(150 + 50 * i), day=1)
    return ents


class Console:
    """Holds the fleet and the startup digests; serves read-only views."""

    def __init__(self, entities) -> None:
        self.entities = entities
        self.digests_at_start = {e.entity_id: e.book.journal_digest()
                                 for e in entities}

    def health(self) -> dict:
        return {"ok": True, "protocol": CONSOLE,
                "entities": len(self.entities), "read_only": True}

    def view(self) -> dict:
        view = consolidated_view(self.entities)    # its own read-only proof
        after = {e.entity_id: e.book.journal_digest() for e in self.entities}
        if after != self.digests_at_start:
            raise ConsoleError("a book changed while the console served — refusing")
        return view


def make_handler(console: Console):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:      # tests stay quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _refuse(self, method: str) -> None:
            body = json.dumps({"error": f"{method} refused — the console is "
                                        "read-only by construction (no write "
                                        "route exists)"}).encode()
            self._send(405, body, "application/json")

        def do_GET(self) -> None:
            try:
                if self.path == "/health":
                    return self._send(200, json.dumps(console.health()).encode(),
                                      "application/json")
                if self.path == "/view.json":
                    return self._send(200,
                                      json.dumps(console.view(), indent=2).encode(),
                                      "application/json")
                if self.path == "/":
                    v = console.view()
                    rows = "".join(
                        f"<tr><td>{html.escape(p['entity'])}</td>"
                        f"<td>{p['cash_muc']}</td><td>{p['revenue_muc']}</td>"
                        f"<td>{'yes' if p['balanced'] else 'NO'}</td>"
                        f"<td>{p['book_digest']}</td></tr>"
                        for p in v["per_entity"])
                    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>DYNAMIS regulator console</title></head><body>
<h1>DYNAMIS regulator console</h1>
<p>{CONSOLE} — read-only by construction. Fleet rollup digest:
<code>{v['rollup_digest']}</code></p>
<table border="1"><tr><th>entity</th><th>cash muc</th><th>revenue muc</th>
<th>balanced</th><th>book digest</th></tr>{rows}</table>
</body></html>"""
                    return self._send(200, page.encode(),
                                      "text/html; charset=utf-8")
                return self._send(404, json.dumps(
                    {"error": f"no route: {self.path}"}).encode(),
                    "application/json")
            except ConsoleError as e:
                return self._send(500, json.dumps({"error": str(e)}).encode(),
                                  "application/json")

        def do_POST(self) -> None:
            self._refuse("POST")

        def do_PUT(self) -> None:
            self._refuse("PUT")

        def do_DELETE(self) -> None:
            self._refuse("DELETE")

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.console.v1 — gate 3.3 console")
    ap.add_argument("cmd", choices=["serve"])
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--host", default="127.0.0.1")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true")
    g.add_argument("--entities", nargs="+", default=None)
    ns = ap.parse_args(argv)
    entities = (demo_fleet() if ns.demo or not ns.entities
                else [instantiate(eid, day=1) for eid in ns.entities])
    console = Console(entities)
    httpd = ThreadingHTTPServer((ns.host, ns.port), make_handler(console))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"dyn.console.v1 — the consolidated view on {ns.host}:{ns.port} "
          f"({len(entities)} entities, read-only by construction); Ctrl-C exits")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
