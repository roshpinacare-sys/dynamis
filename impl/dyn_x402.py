#!/usr/bin/env python3
"""dyn.x402.v1 — the paid-HTTP door: x402 rails + A2A card over the engine.

Gate 2.4's rails, reference implementation: an external machine client that
speaks plain HTTP can buy, drive and settle a job without ever reading this
codebase. The x402 pattern maps onto DYNAMIS exactly — the 402 challenge *is*
the escrow terms, and payment *is* escrow funding (fail-closed by the engine,
not by the web layer):

  POST /jobs                → 402 + X-PAYMENT-REQUIRED (base64url escrow terms)
  POST /jobs/<id>/payment   → the client pays by funding escrow → 201 (Law 9 class)
  POST /jobs/<id>/work      → artifact bytes (base64) enter the job folder
  POST /jobs/<id>/check     → the evidence harness runs on the shipped bytes
  POST /jobs/<id>/settle    → payout from escrow — all-PASS evidence or nothing
  GET  /.well-known/agent-card.json  → the A2A discovery card (skills + payment)

Discovery: an agent finds the endpoint through its A2A card, learns the payment
scheme from the 402 itself, and needs no custody setup to *try* — the same
front-door rule as the skill. Engine rule violations (settling an open job,
double settle) surface as 409; skipped steps never silently pass.

  python3 dyn_x402.py serve --port 8091     # the endpoint
  python3 dyn_x402.py demo                  # server + external client, localhost

Stdlib only (ADR-0007). In this reference, escrow funding is the in-process
rail; production verifies the funding signature at the HSM (gate 2.4 hardening).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_engine import EngineError, WorkLoop  # noqa: E402
from dynamis_core import usds  # noqa: E402

PROTOCOL = "dyn.x402.v1"
ENTITY = "ent-001"
REVENUE_REF = "env-ops-001"
MAX_ARTIFACT = 64 * 1024
CURRENCIES = ("USD", "EUR")

CARD = {
    "name": "dynamis-job-rail",
    "description": "Escrowed, evidence-verified agent jobs over plain HTTP: "
                   "pay by funding escrow, settle by proof (Law 19).",
    "protocol": PROTOCOL,
    "version": "1.0.0",
    "provider": {"organization": "DYNAMIS", "url":
                 "https://roshpinacare-sys.github.io/dynamis/"},
    "capabilities": {"streaming": False, "pushNotifications": False,
                     "stateTransitionHistory": True},
    "skills": [
        {"id": "buy_job", "name": "Buy a verified job",
         "description": "POST /jobs → 402 escrow terms → pay → work → check → "
                        "settle. Payment is escrow; refunds are automatic on FAIL."},
        {"id": "settle_by_evidence", "name": "Settle by evidence",
         "description": "Payout requires all-PASS evidence records on the "
                        "shipped bytes; no evidence, no payout path exists."},
        {"id": "publish_receipt", "name": "Publish the receipt",
         "description": "Settled work becomes a dyn.post.v1 object with the "
                        "artifact hash-bound — a portable, verifiable portfolio."},
    ],
    "payment": {"schemes": [{"scheme": "dyn-escrow", "asset": "USDS",
                             "min_amount_usds": 120,
                             "description": "escrow is the payment; the ladder "
                                            "prices the verification class"}]},
}


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(obj, sort_keys=True).encode()).decode()


def _unb64(s: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(s.encode()))


# --------------------------------------------------------------------------
# the server: the engine behind HTTP, nothing more
# --------------------------------------------------------------------------
class DynamisRail:
    """State and dispatch, separate from the socket loop — unit-testable."""

    def __init__(self, *, root: str | Path | None = None,
                 entity: str = ENTITY) -> None:
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="dyn-x402-"))
        self.own_root = root is None
        self.entity = entity
        self.challenges: dict[str, dict] = {}
        self.loops: dict[str, WorkLoop] = {}
        self.lock = threading.Lock()

    # ---------- route table ----------
    def dispatch(self, method: str, path: str, body: dict | None) -> tuple[int, dict]:
        try:
            if method == "GET" and path == "/health":
                return 200, {"ok": True, "protocol": PROTOCOL}
            if method == "GET" and path == "/.well-known/agent-card.json":
                return 200, CARD
            parts = [p for p in path.split("/") if p]
            if method == "POST" and parts == ["jobs"]:
                return self._offer(body or {})
            if len(parts) == 2 and parts[0] == "jobs" and method == "GET":
                return self._status(parts[1])
            if len(parts) == 3 and parts[0] == "jobs":
                job_id, action = parts[1], parts[2]
                if method == "POST" and action == "payment":
                    return self._pay(job_id, body or {})
                if method == "POST" and action == "work":
                    return self._work(job_id, body or {})
                if method == "POST" and action == "check":
                    return self._check(job_id, body or {})
                if method == "POST" and action == "settle":
                    return self._settle(job_id, body or {})
                if method == "POST" and action == "refund":
                    return self._refund(job_id, body or {})
            return 404, {"error": f"no route: {method} {path}"}
        except EngineError as e:
            return 409, {"error": str(e)}
        except (KeyError, TypeError, ValueError) as e:
            return 400, {"error": f"bad request: {e}"}

    # ---------- the 402 flow ----------
    def _offer(self, body: dict) -> tuple[int, dict]:
        job_id = body.get("job_id") or f"job-x402-{len(self.challenges) + 1:04d}"
        value_usds = int(body.get("value_usds", 250))
        terms = {
            "scheme": "dyn-escrow", "asset": "USDS",
            "pay_to": self.entity, "resource": f"/jobs/{job_id}",
            "maxAmountRequired": value_usds, "job_id": job_id,
            "description": "funding this escrow opens the job; class is priced "
                           "by Law 9 at open; FAIL refunds in full",
        }
        with self.lock:
            self.challenges[job_id] = terms
        return 402, {"x-payment-required": terms,
                     "how": "POST the terms with {payer: <agent-id>} to "
                            f"/jobs/{job_id}/payment"}

    def _pay(self, job_id: str, body: dict) -> tuple[int, dict]:
        with self.lock:
            terms = self.challenges.get(job_id)
        if not terms:
            return 404, {"error": f"no open offer for {job_id}"}
        if job_id in self.loops:
            return 409, {"error": "job already funded"}
        payer = str(body.get("payer", "")).strip()
        if not payer:
            return 400, {"error": "payment requires payer (agent id)"}
        paid = int(body.get("amount_usds", terms["maxAmountRequired"]))
        if paid != terms["maxAmountRequired"]:
            return 402, {"x-payment-required": terms,
                         "error": f"amount mismatch: escrow needs exactly "
                                  f"{terms['maxAmountRequired']} USDS"}
        day = int(body.get("day", 1))
        loop = WorkLoop(self.root / job_id)
        loop.job_new(job_id=job_id, entity_id=self.entity,
                     revenue_ref=REVENUE_REF, value_muc=usds(paid),
                     deadline_day=day + 7, seed=int(body.get("seed", 1000)),
                     count=int(body.get("count", 250)), currencies=CURRENCIES,
                     buyer_count=20, day=day)
        with self.lock:
            self.loops[job_id] = loop
        j = loop.log["job"]
        return 201, {"job_id": job_id, "status": "open", "payer": payer,
                     "verification_class": j["verification_class"],
                     "escrow_muc": j["escrow_usds_muc"],
                     "input_sha256": j["spec"]["input_sha256"]}

    # ---------- the loop over HTTP ----------
    def _require_funded(self, job_id: str) -> tuple[WorkLoop | None, tuple[int, dict] | None]:
        with self.lock:
            loop = self.loops.get(job_id)
            terms = self.challenges.get(job_id)
        if not loop:
            if terms:
                return None, (402, {"x-payment-required": terms,
                                    "error": "job not funded — pay first"})
            return None, (404, {"error": f"unknown job {job_id}"})
        return loop, None

    def _work(self, job_id: str, body: dict) -> tuple[int, dict]:
        loop, err = self._require_funded(job_id)
        if err:
            return err
        art_b64 = body.get("artifact_b64", "")
        raw = base64.b64decode(art_b64) if art_b64 else b""
        if not raw:
            return 400, {"error": "artifact_b64 (base64 of the artifact) required"}
        if len(raw) > MAX_ARTIFACT:
            return 413, {"error": f"artifact exceeds {MAX_ARTIFACT} bytes"}
        src = self.root / f"{job_id}-incoming.py"
        src.write_bytes(raw)
        with self.lock:
            out = loop.work(src)
        src.unlink(missing_ok=True)
        return 200, dict(out)

    def _check(self, job_id: str, body: dict) -> tuple[int, dict]:
        loop, err = self._require_funded(job_id)
        if err:
            return err
        with self.lock:
            return 200, loop.check(day=int(body.get("day", 2)))

    def _settle(self, job_id: str, body: dict) -> tuple[int, dict]:
        loop, err = self._require_funded(job_id)
        if err:
            return err
        worker = str(body.get("worker_id", "agent-http-1"))
        with self.lock:
            out = loop.settle(day=int(body.get("day", 10)), worker_id=worker,
                              persona=f"{worker}.persona",
                              keyref=f"hsm:kr-{worker}")
        return 200, out

    def _refund(self, job_id: str, body: dict) -> tuple[int, dict]:
        loop, err = self._require_funded(job_id)
        if err:
            return err
        with self.lock:
            return 200, loop.refund(day=int(body.get("day", 10)),
                                    worker_id=str(body.get("worker_id",
                                                           "agent-http-1")))

    def _status(self, job_id: str) -> tuple[int, dict]:
        loop, err = self._require_funded(job_id)
        if err:
            return err
        j = loop.log["job"]
        return 200, {"job_id": j["job_id"], "status": loop.log["status"],
                     "verification_class": j["verification_class"],
                     "escrow_muc": j["escrow_usds_muc"],
                     "evidence_records": len(loop.log.get("evidence", [])),
                     "history": [h["kind"] for h in loop.log.get("history", [])]}


class RailHandler(BaseHTTPRequestHandler):
    rail: DynamisRail  # class attribute, set by serve()

    def log_message(self, *args) -> None:      # quiet under tests
        pass

    def _reply(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if code == 402 and "x-payment-required" in obj:
            self.send_header("X-PAYMENT-REQUIRED", _b64(obj["x-payment-required"]))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        if self.headers.get("Content-Type", "").startswith("application/json"):
            return json.loads(raw)
        return {}

    def do_GET(self) -> None:                  # noqa: N802 (http.server API)
        code, obj = self.rail.dispatch("GET", self.path, None)
        self._reply(code, obj)

    def do_POST(self) -> None:                 # noqa: N802
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            self._reply(400, {"error": "body is not valid JSON"})
            return
        code, obj = self.rail.dispatch("POST", self.path, body)
        self._reply(code, obj)


def make_server(rail: DynamisRail | None = None) -> tuple[ThreadingHTTPServer, DynamisRail]:
    """Bind 127.0.0.1:0 (ephemeral) — tests and the demo pick the port up."""
    rail = rail or DynamisRail()
    handler = type("BoundRailHandler", (RailHandler,), {"rail": rail})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    return srv, rail


# --------------------------------------------------------------------------
# the reference external client — plain HTTP, no imports from the engine
# --------------------------------------------------------------------------
class X402Client:
    """What an external machine client looks like: urllib and nothing else."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _call(self, method: str, path: str, body: dict | None = None
              ) -> tuple[int, dict, dict]:
        req = urllib.request.Request(self.base + path, method=method)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data, timeout=30) as r:
                return r.status, json.loads(r.read()), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), dict(e.headers)

    def discover(self) -> dict:
        _, card, _ = self._call("GET", "/.well-known/agent-card.json")
        return card

    def buy_job(self, *, value_usds: int, count: int = 250, seed: int = 1000,
                payer: str = "agent-external-1", artifact: bytes,
                day: int = 1) -> dict:
        """The whole x402 dance: offer → 402 → pay → work → check → settle."""
        code, offer, hdrs = self._call("POST", "/jobs", {
            "value_usds": value_usds, "count": count, "seed": seed})
        if code != 402:
            raise RuntimeError(f"expected 402, got {code}: {offer}")
        terms = offer["x-payment-required"]
        assert _unb64(hdrs["X-PAYMENT-REQUIRED"]) == terms, "header/body terms differ"
        code, opened, _ = self._call("POST", terms["resource"] + "/payment", {
            "payer": payer, "amount_usds": terms["maxAmountRequired"], "day": day})
        if code != 201:
            raise RuntimeError(f"payment refused: {code} {opened}")
        code, worked, _ = self._call("POST", terms["resource"] + "/work", {
            "artifact_b64": base64.b64encode(artifact).decode()})
        if code != 200:
            raise RuntimeError(f"work refused: {code} {worked}")
        code, checked, _ = self._call("POST", terms["resource"] + "/check",
                                      {"day": day + 1})
        if code != 200:
            raise RuntimeError(f"check failed: {code} {checked}")
        code, settled, _ = self._call("POST", terms["resource"] + "/settle",
                                      {"day": day + 10, "worker_id": payer})
        if code != 200:
            raise RuntimeError(f"settle refused: {code} {settled}")
        return {"offer": terms, "opened": opened, "check": checked,
                "settle": settled}


def demo() -> int:
    srv, rail = make_server()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    from dyn_engine import ARTIFACT_INVOICE_PARSER
    client = X402Client(base)
    card = client.discover()
    print(f"{PROTOCOL} — external client buys a verified job from {base}")
    print(f"  card: {card['name']} · skills: {[s['id'] for s in card['skills']]}")
    r = client.buy_job(value_usds=500, count=500, seed=30161,
                       artifact=ARTIFACT_INVOICE_PARSER.encode())
    o, c, s = r["offer"], r["check"], r["settle"]
    print(f"  402 terms: {o['maxAmountRequired']} USDS escrow → {o['resource']}")
    print(f"  opened: class {r['opened']['verification_class']}, "
          f"escrow {r['opened']['escrow_muc']:,} µ¢")
    print(f"  check: {c['overall']} on {c['records']} evidence records "
          f"({c['runtime_s']}s)")
    print(f"  settled: payout {s['payout_muc']:,} µ¢, fee {s['fee_muc']:,} µ¢, "
          f"emitted {s['emitted_dyn_mu']:,} µDYN, chain ok: {s['chain_ok']}")
    srv.shutdown()
    print("  the external machine client completed a paid job via x402 — "
          "gate 2.4's acceptance line, in-repo.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dyn_x402",
                                 description="DYNAMIS paid-HTTP rail (dyn.x402.v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8091)
    p.add_argument("--root", default=None, help="job folders live here")
    sub.add_parser("demo")
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        return demo()
    rail = DynamisRail(root=a.root) if a.root else DynamisRail()
    handler = type("BoundRailHandler", (RailHandler,), {"rail": rail})
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    print(f"{PROTOCOL} serving on http://127.0.0.1:{a.port} — card at "
          f"/.well-known/agent-card.json")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
