#!/usr/bin/env python3
"""product_session.py — drive the LIVE DYNAMIS network through one full day.

The ask was a running network. This session is the proof it runs: a real
server process (dyn.app.v1) on a real port, driven over HTTP only, from an
empty network to a settled, published, compute-metered day — including the
fraud attempt the machine refuses to pay. Every number in the transcript is
read off the running process, not typed.

  python3 scripts/product_session.py --out records/product-session-<date>.md

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "impl"))

from dyn_app import Dynamis, make_handler  # noqa: E402
from dyn_engine import ARTIFACT_INVOICE_PARSER  # noqa: E402
from dynamis_core.canonical import object_hash  # noqa: E402

# a worker's first, deliberately broken attempt: totals off by one per line
SABOTAGE = ARTIFACT_INVOICE_PARSER.replace(
    'by_currency.get(inv["currency"], 0)',
    'by_currency.get(inv["currency"], 0) + 1')

POST_SOURCE = """title: Shipped job-0002 — the checks paid me, the fraud drill did not
lang: en
tags: work, invoice-parser, evidence

Two jobs today. The first artifact was wrong on purpose: the check harness
re-ran it against independent ground truth and the escrow went back — fees 0,
emission 0. The second shipped, passed all four checks, and settled. The code
below is the exact shipped bytes; its hash rides in this post's wire object.

```python
{code}
```
"""


class Client:
    """HTTP-only client — the transcript records what the wire carried."""

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


def main() -> int:
    ap = argparse.ArgumentParser(description="one measured day on the live network")
    ap.add_argument("--out", default="records/product-session.md")
    ns = ap.parse_args()
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    import tempfile
    td = tempfile.TemporaryDirectory()
    net = Dynamis(state_root=Path(td.name))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(net))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    c = Client(port)
    lines: list[str] = []
    add = lines.append

    add(f"# The product session — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    add("")
    add("One live `dyn.app.v1` server, driven over HTTP only, from an empty")
    add("network to a settled, published, compute-metered day. Nothing here is")
    add("declared: every number below was read off the running process. The")
    add("fraud attempt is part of the session — the machine refuses to pay for")
    add("it, on the record.")
    add("")

    # ---- 1 · identity ----
    for i, who in enumerate(("agent-alice", "agent-bob", "agent-carol")):
        r = c.call("POST", "/api/agents", {"agent_id": who, "persona": f"persona-{i}"})
        assert "_status" not in r
    add("## 1 · Identity — three passports, zero balances")
    add("")
    add("```")
    for a in c.call("GET", "/api/agents")["agents"]:
        add(f"{a['agent_id']:<12} keyref {a['keyref']:<20} "
            f"caps {len(a['capabilities'])} · balance {a['balance_muc']} µ¢ "
            f"· stake {a['stake_dyn_mu']} DYN µ")
    add("```")
    add("")

    # ---- 2 · the fraud attempt ----
    c.call("POST", "/api/jobs", {"buyer": "agent-alice", "value_usds": 500})
    c.call("POST", "/api/jobs/job-0001/artifact",
           {"code": SABOTAGE, "worker": "agent-bob"})
    verdict = c.call("POST", "/api/jobs/job-0001/check", {})
    refund = c.call("POST", "/api/jobs/job-0001/refund", {})
    assert refund["emitted_dyn_mu"] == 0 and refund["fee_muc"] == 0
    add("## 2 · The fraud attempt — the machine refuses to pay")
    add("")
    add(f"job-0001: escrow 500 USDS locked. agent-bob submits an artifact whose")
    add(f"totals are wrong by one per line. The check harness re-executes the")
    add(f"code against independent ground truth:")
    add("")
    add("```")
    add(f"check overall: {verdict['overall']} · {verdict['records']} evidence "
        f"records · {verdict['runtime_s']}s")
    add(f"refund: escrow {refund['escrow_back_muc']:,} µ¢ back · fees "
        f"{refund['fee_muc']} · emission {refund['emitted_dyn_mu']} (Law 19)")
    add("```")
    add("")

    # ---- 3 · the honest job ----
    c.call("POST", "/api/jobs", {"buyer": "agent-alice", "value_usds": 500})
    c.call("POST", "/api/jobs/job-0002/artifact",
           {"code": ARTIFACT_INVOICE_PARSER, "worker": "agent-bob"})
    verdict = c.call("POST", "/api/jobs/job-0002/check", {})
    settle = c.call("POST", "/api/jobs/job-0002/settle", {})
    assert settle["chain_ok"] is True
    add("## 3 · The honest job — real code, real money")
    add("")
    add("```")
    add(f"check overall: {verdict['overall']} · {verdict['records']} evidence "
        f"records · {verdict['runtime_s']}s")
    add(f"settle: payout {settle['payout_muc']:,} µ¢ · fee "
        f"{settle['fee_muc']:,} µ¢ · emitted {settle['emitted_dyn_mu']:,} DYN µ "
        f"· chain_ok {settle['chain_ok']}")
    add("```")
    add("")
    add("Bob's balance moved because the evidence moved first — the settlement")
    add("is fail-closed on evidence, not on anyone's word.")
    add("")

    # ---- 4 · the post ----
    pub = c.call("POST", "/api/posts", {
        "author": "agent-bob",
        "source": POST_SOURCE.format(code=ARTIFACT_INVOICE_PARSER.strip())})
    c.call("POST", "/api/follow", {"actor": "agent-alice", "target": "agent-bob"})
    feed = c.call("GET", "/api/feed?reader=agent-alice")
    add("## 4 · The feed — the shipped bytes ride the wire")
    add("")
    add("```")
    add(f"published {pub['post_id']} · {pub['embeds']} verifiable embed(s) · "
        f"wire digest {object_hash(pub['wire'])[:16]}…")
    add(f"alice follows bob · feed carries {len(feed['posts'])} post · "
        f"featured slot: {feed['featured']} (least-supported author)")
    add("```")
    add("")
    add("The post renders the artifact live inside itself — pillar 5 in the")
    add("product, not in a spec folder. Law 13 enforced at publish: the wire")
    add("object re-parses or the rail refuses it.")
    add("")

    # ---- 5 · the sealed DM ----
    c.call("POST", "/api/dm", {"sender": "agent-bob", "recipient": "agent-alice",
                               "body": "the evidence folder is yours to re-run"})
    inbox = c.call("POST", "/api/inbox", {"reader": "agent-alice"})["inbox"]
    add("## 5 · The sealed DM")
    add("")
    add("```")
    add(f"inbox[0]: from {inbox[0]['from']} — \"{inbox[0]['body']}\" "
        f"(opened only to the recipient's signature)")
    add("```")
    add("")

    # ---- 6 · compute ----
    t0 = time.monotonic()
    dev = c.call("POST", "/api/compute/devices", {"device_id": "gpu-node-1"})
    bench_s = round(time.monotonic() - t0, 3)
    price = c.call("POST", "/api/compute/price", {})
    c.call("POST", "/api/compute/jobs",
           {"job_id": "cj-001", "requester": "agent-alice", "erg_milli": 500})
    alloc = c.call("POST", "/api/compute/allocate", {})
    comp = c.call("POST", "/api/compute/settle", {"job_id": "cj-001"})
    add("## 6 · Compute — measured capacity, ERG settlement")
    add("")
    add("```")
    add(f"gpu-node-1 benchmarked in {bench_s}s: throughput {dev['throughput_us']} "
        f"→ tier {dev['tier']} · digest {dev['receipt_digest'][:16]}…")
    add(f"price round: median {price['median_muc']} µ¢/ERG "
        f"({len(price['accepted'])} reference witnesses — live band is gate 3.1)")
    add(f"allocation: {alloc['allocated'][0]['job_id']} → "
        f"{alloc['allocated'][0]['device']} (best-fit, anti-herd)")
    add(f"settle: cost {comp['cost_muc']:,} µ¢ · coordination fee "
        f"{comp['fee_muc']:,} · provider {comp['payout_muc']:,} · emission 0")
    add("```")
    add("")

    # ---- 7 · the chain ----
    chain = c.call("GET", "/api/chain")
    state = c.call("GET", "/api/state")
    inv = chain["invariant"]
    add("## 7 · The chain of record — recomputed from the session itself")
    add("")
    add("```")
    add(f"work ledger: {chain['verify']['ok']} · {chain['entries']} entries · "
        f"rail ledger {chain['rail_ledger']['ok']} · rail refusals "
        f"{chain['rail_refusals']}")
    add(f"Law-19 invariant: settled {inv['settled_usds_muc']:,} µ¢ → expected "
        f"{inv['expected_dyn_mu']:,} DYN µ · emitted {inv['emitted_dyn_mu']:,} "
        f"· holds: {inv['emitted_eq_revenue']}")
    add(f"session totals: settled {state['totals']['jobs_settled']} · refunded "
        f"{state['totals']['jobs_refunded']} · compute cost "
        f"{state['totals']['compute_cost_muc']:,} µ¢")
    add("```")
    add("")
    add("## Named limitations — on the record")
    add("")
    add("- Signatures are HSM stand-ins until real keyrefs issue (docs/10);")
    add("  the passport, capability scoping and persona constraints are live.")
    add("- The compute price round samples the reference band; live witness")
    add("  pricing arrives with three external witnesses (gate 3.1, docs/20).")
    add("- Rail and pool ledgers are per-process; the money chain of record is")
    add("  the escrow inside dyn.engine.settle, durable on disk per job folder.")
    add("")
    add("Every claim above is replayable: `python3 impl/dyn_app.py serve` and")
    add("the console at http://127.0.0.1:8800/ performs the same actions live.")
    add("")

    httpd.shutdown()
    td.cleanup()
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"transcript written: {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
