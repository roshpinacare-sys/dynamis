#!/usr/bin/env python3
"""dyn.engine.v1 — the DYNAMIS work-loop engine.

Pattern credit: `storytold/craft-anything` (study → build → check → refine; evidence
records with confidence, coverage and limitations; agent-first CLI). DYNAMIS runs the
same loop where it pays — open → work → check → (refine) → settle → post — with three
differences that make it an economy instead of a workshop:

  1. every step is a protocol object (schemas/*.json), not just a local artifact;
  2. every check writes a machine-readable evidence record — verdict, class, coverage,
     and honest limitations;
  3. settlement is fail-closed on evidence: no PASS evidence, no payout path (Law 19).

A job is a folder, the way a craft-anything project is a folder:

    dyn-job.json     the worklog: request, target, status, history, evidence index
    inputs/          the target (deterministic input generated at job_new)
    artifact/        the work (built by any coding agent — the engine is agnostic)
    evidence/        check records (checks/)
    post/            the published dyn.post.v1 object + rendered preview

Each CLI subcommand is one tool call for an agent. MCP/ACP wrappers land at gate 2.4
(docs/04-integration.md §3); the loop is already drivable end to end:

    python3 dyn_engine.py job_new jobs/demo --job-id job-demo-001
    python3 dyn_engine.py work    jobs/demo artifact.py
    python3 dyn_engine.py check   jobs/demo
    python3 dyn_engine.py settle  jobs/demo
    python3 dyn_engine.py post    jobs/demo
    python3 dyn_engine.py demo

Stdlib only (ADR-0007). The worklog is the agent-side record; the hash-chained escrow
events inside dynamis_core remain the protocol record of the money.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core import (Claim, EmissionLedger, JobMachine, accrue, floor_class,
                          object_hash, usds)
from agent_kit import AgentKit, witness_verdict
import dyn_post

ENGINE = "dyn.engine.v1"
STATUS_OPEN, STATUS_WORKING = "open", "working"
STATUS_PASS, STATUS_FAIL, STATUS_SETTLED = "checked_pass", "checked_fail", "settled"


class EngineError(ValueError):
    """The loop refuses to continue. Fail-closed, with the reason on record."""


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


class WorkLoop:
    """One job folder: the craft-anything project shape, wired to the protocol."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.log_path = self.root / "dyn-job.json"
        self.log: dict = _read_json(self.log_path) if self.log_path.exists() else {}

    # ---------- history ----------
    def _history(self, kind: str, **detail) -> None:
        seq = max((h["seq"] for h in self.log.get("history", [])), default=0) + 1
        self.log.setdefault("history", []).append({"seq": seq, "kind": kind, **detail})

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _write_json(self.log_path, self.log)

    # ---------- 1. open ----------
    def job_new(self, *, job_id: str, entity_id: str, revenue_ref: str,
                value_muc: int, deadline_day: int, seed: int, count: int,
                currencies: tuple[str, ...], buyer_count: int, day: int) -> dict:
        if self.log:
            raise EngineError(f"{self.root} is already a job folder ({self.log['job']['job_id']})")
        cls = floor_class(value_muc)
        job = {"job_id": job_id, "entity_id": entity_id,
               "spec": {"task": "parse_invoice_batch", "seed": seed, "count": count,
                        "currencies": list(currencies), "buyer_count": buyer_count,
                        "output_contract": "invoice-results-v1",
                        "max_runtime_s": 10,
                        "input_sha256": None},  # filled below
               "escrow_usds_muc": value_muc, "deadline_day": deadline_day,
               "verification_class": cls, "revenue_ref": revenue_ref}
        inputs = generate_invoice_batch(seed=seed, count=count,
                                        currencies=currencies, buyers=buyer_count)
        inp = self.root / "inputs" / "batch.json"
        inp.parent.mkdir(parents=True, exist_ok=True)
        _write_json(inp, inputs)
        job["spec"]["input_sha256"] = _sha256_file(inp)
        self.log = {"engine": ENGINE, "job": job,
                    "target": {"output_contract": "invoice-results-v1",
                               "checks": ["artifact_runs", "contract_shape",
                                          "totals_match_ground_truth",
                                          "bounded_runtime"]},
                    "status": STATUS_OPEN, "history": [], "evidence": [],
                    "artifact": None, "post": None}
        self._history("open", job_id=job_id, escrow_usds_muc=value_muc,
                      verification_class=cls, count=count, seed=seed)
        self._save()
        return job

    # ---------- 2. work ----------
    def work(self, artifact_src: str | Path) -> dict:
        self._require_status((STATUS_OPEN, STATUS_WORKING, STATUS_FAIL, STATUS_PASS))
        src = Path(artifact_src)
        if not src.is_file():
            raise EngineError(f"artifact {src} not found")
        dest = self.root / "artifact" / "invoice_parser.py"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text())
        self.log["artifact"] = {"path": "artifact/invoice_parser.py",
                                "sha256": _sha256_file(dest),
                                "bytes": dest.stat().st_size}
        self.log["status"] = STATUS_WORKING
        self._history("work", sha256=self.log["artifact"]["sha256"],
                      bytes=self.log["artifact"]["bytes"])
        self._save()
        return self.log["artifact"]

    # ---------- 3. check ----------
    def check(self, *, day: int) -> dict:
        self._require_status((STATUS_WORKING, STATUS_FAIL, STATUS_PASS))
        if not self.log["artifact"]:
            raise EngineError("no artifact submitted — run `work` first")
        art = self.root / "artifact" / "invoice_parser.py"
        inp = self.root / "inputs" / "batch.json"
        if _sha256_file(inp) != self.log["job"]["spec"]["input_sha256"]:
            raise EngineError("inputs were modified after job_new — target integrity broken")
        ev_dir = self.root / "evidence"
        # a new check run replaces the previous evidence index (the refine loop):
        # only the latest run's records may vouch for settlement
        if ev_dir.exists():
            import shutil
            shutil.rmtree(ev_dir)
        ev_dir.mkdir(parents=True)
        self.log["evidence"] = []
        records: list[dict] = []

        # check 1 — the artifact actually runs (class B instrument)
        out = self.root / "evidence" / "artifact_output.json"
        t0 = time.monotonic()
        proc = subprocess.run(
            [sys.executable, str(art), str(inp), str(out)],
            capture_output=True, text=True, timeout=60)
        runtime = time.monotonic() - t0
        records.append(dict(
            check="artifact_runs", cls="B", verdict="PASS" if proc.returncode == 0 else "FAIL",
            confidence=1.0, coverage="process exits cleanly and writes its contract output",
            limitations="does not judge correctness — later checks do",
            measured={"returncode": proc.returncode,
                      "stderr_tail": proc.stderr.strip()[-200:]},
            runtime_s=round(runtime, 4)))

        got: dict | None = None
        if proc.returncode == 0:
            try:
                got = _read_json(out)
            except (json.JSONDecodeError, OSError):
                got = None
            spec = self.log["job"]["spec"]

            # check 2 — output contract shape (class A: deterministic)
            keys = {"batch", "count", "lines", "by_currency"}
            ok_shape = (isinstance(got, dict) and set(got) == keys
                        and isinstance(got.get("count"), int) and isinstance(got.get("lines"), int)
                        and isinstance(got.get("batch"), str)
                        and isinstance(got.get("by_currency"), dict)
                        and all(isinstance(v, int) for v in got["by_currency"].values())
                        and got["count"] == spec["count"]
                        and got["batch"] == inputs_batch_id(inp))
            records.append(dict(
                check="contract_shape", cls="A", verdict="PASS" if ok_shape else "FAIL",
                confidence=1.0, coverage="exact key set, integer-only values (canonical rule), batch id, count",
                limitations="shape only; totals are the next check's job"))

            # check 3 — totals vs independently computed ground truth (class A)
            want = ground_truth(inp)
            ok_totals = bool(got) and got["lines"] == want["lines"] and \
                got["by_currency"] == want["by_currency"]
            records.append(dict(
                check="totals_match_ground_truth", cls="A",
                verdict="PASS" if ok_totals else "FAIL", confidence=1.0,
                coverage="per-currency totals and line count against an independent aggregation",
                limitations="same-input double implementation; catches aggregation bugs, not input bugs"))

            # check 4 — bounded runtime (class B)
            ok_rt = runtime <= spec["max_runtime_s"]
            records.append(dict(
                check="bounded_runtime", cls="B", verdict="PASS" if ok_rt else "FAIL",
                confidence=0.99, coverage=f"wall clock under {spec['max_runtime_s']}s on the runner",
                limitations="single runner; no cross-device variance sampled here"))

        for i, r in enumerate(records, 1):
            r = {"n": f"{i:03d}", "engine": ENGINE, "day": day,
                 "artifact_sha256": self.log["artifact"]["sha256"], **r}
            _write_json(ev_dir / f"{r['n']}-{r['check']}.json", r)
            self.log["evidence"].append(f"evidence/{r['n']}-{r['check']}.json")

        verdicts = [r["verdict"] for r in records]
        overall = "PASS" if verdicts and all(v == "PASS" for v in verdicts) else "FAIL"
        self.log["status"] = STATUS_PASS if overall == "PASS" else STATUS_FAIL
        self._history("check", overall=overall,
                      checks=[r["check"] for r in records],
                      failed=[r["check"] for r in records if r["verdict"] != "PASS"])
        self._save()
        return {"overall": overall, "records": len(records),
                "runtime_s": round(runtime, 4)}

    # ---------- 4. settle (fail-closed on evidence) ----------
    def settle(self, *, day: int, worker_id: str = "agent-honest-1",
               persona: str = "honest.persona", keyref: str = "hsm:kr-honest") -> dict:
        self._require_status((STATUS_PASS,))
        # re-verify the evidence on disk before any money moves
        for rel in self.log["evidence"]:
            rec = _read_json(self.root / rel)
            if rec["verdict"] != "PASS":
                raise EngineError(f"evidence {rel} is not a PASS record")
        led = EmissionLedger()
        entity = AgentKit(self.log["job"]["entity_id"], "entity-rail",
                          "hsm:kr-entity", role="entity")
        worker = AgentKit(worker_id, persona, keyref, stake_dyn_mu=2_500_000, day=day)
        j = self.log["job"]
        machine = entity.open_job(j["job_id"], j["entity_id"], j["spec"],
                                  j["escrow_usds_muc"], j["deadline_day"],
                                  j["revenue_ref"])
        machine.fire("claim", worker=worker_id)
        receipt = object_hash({"evidence": self.log["evidence"],
                               "artifact": self.log["artifact"]["sha256"]})
        claim = Claim(f"cl-{j['job_id']}-{worker_id}", j["job_id"], worker_id,
                      (self.log["artifact"]["sha256"],), receipt, day)
        machine.fire("deliver", claim=claim)
        machine.fire("start_verify")
        # the check harness *is* the re-execution: it ran the artifact and compared
        witness_verdict(machine, n_workers=1, reexec_matches=True, seed=day)
        result = worker.settle(machine, led)
        self.log["status"] = STATUS_SETTLED
        self._history("settle", payout_muc=result["payout_muc"],
                      fee_muc=result["fee_muc"],
                      emitted_dyn_mu=result["emitted_dyn_mu"],
                      chain_ok=result["chain_ok"])
        self._save()
        return result

    # ---------- 5. post ----------
    def post(self, *, day: int, post_id: str) -> dict:
        self._require_status((STATUS_SETTLED,))
        art = self.root / "artifact" / "invoice_parser.py"
        j = self.log["job"]
        body = f"""title: Shipped {j['job_id']} — verified, with its own proof
lang: en
tags: jobs, invoice-parser, verified

Settled on day {day}: {j['spec']['count']} invoices, escrow {j['escrow_usds_muc'] // 1_000_000} USDS,
verification class {j['verification_class']}. The artifact below is the shipped
bytes — its hash is in the wire object, the evidence records are in the job folder.

```python
{art.read_text().strip()}
```

ראייה במקום הצהרה: הצ'קים רצים על הבייטים האלה ממש, והתשלום מותנה בעבירה.
"""
        post = dyn_post.parse_post(body)
        wire = dyn_post.to_wire(post, post_id=post_id, author="agent-honest-1", day=day)
        pdir = self.root / "post"
        pdir.mkdir(exist_ok=True)
        _write_json(pdir / "post.wire.json", wire)
        (pdir / "preview.html").write_text(dyn_post.render_post(post))
        self.log["post"] = {"wire": "post/post.wire.json",
                            "preview": "post/preview.html",
                            "embeds": len(wire["embeds"])}
        self._history("post", post_id=post_id, embeds=len(wire["embeds"]))
        self._save()
        return wire

    # ---------- guard ----------
    def _require_status(self, allowed: tuple[str, ...]) -> None:
        if not self.log:
            raise EngineError(f"{self.root} is not a job folder — run job_new")
        if self.log["status"] not in allowed:
            raise EngineError(f"status is {self.log['status']!r}; this step needs one of "
                              f"{', '.join(allowed)} — the loop refuses to skip steps")


# --------------------------------------------------------------------------
# the target: deterministic batch + independent ground truth
# --------------------------------------------------------------------------
def generate_invoice_batch(*, seed: int, count: int,
                           currencies: tuple[str, ...], buyers: int) -> dict:
    rng = random.Random(seed)
    invoices = []
    for i in range(count):
        lines = [{"qty": rng.randint(1, 9), "unit_cents": rng.randrange(150, 9_900)}
                 for _ in range(rng.randint(1, 4))]
        invoices.append({"id": f"inv-{i:05d}",
                         "currency": currencies[i % len(currencies)],
                         "buyer": f"b-{rng.randint(1, buyers):03d}",
                         "lines": lines})
    return {"batch": f"batch-seed-{seed}", "invoices": invoices}


def inputs_batch_id(inp: Path) -> str:
    return _read_json(inp)["batch"]


def ground_truth(inp: Path) -> dict:
    """Independent aggregation — deliberately NOT the artifact's code path."""
    data = _read_json(inp)
    by_cur: dict[str, int] = {}
    lines = 0
    for inv in data["invoices"]:
        for ln in inv["lines"]:
            by_cur[inv["currency"]] = by_cur.get(inv["currency"], 0) + ln["qty"] * ln["unit_cents"]
            lines += 1
    return {"lines": lines, "by_currency": dict(sorted(by_cur.items()))}


# --------------------------------------------------------------------------
# the bundled build — what a coding agent would have produced in `work`
# --------------------------------------------------------------------------
ARTIFACT_INVOICE_PARSER = '''#!/usr/bin/env python3
"""invoice_parser.py — artifact for job spec `parse_invoice_batch` (invoice-results-v1).

Usage: python3 invoice_parser.py <batch.json> <output.json>
Contract: {"batch": str, "count": int, "lines": int, "by_currency": {cur: cents}} —
integers only (canonical rule), totals per currency over qty * unit_cents.
"""
import json
import sys


def parse(batch: dict) -> dict:
    by_currency = {}
    lines = 0
    for inv in batch["invoices"]:
        for ln in inv["lines"]:
            by_currency[inv["currency"]] = (by_currency.get(inv["currency"], 0)
                                            + ln["qty"] * ln["unit_cents"])
            lines += 1
    return {"batch": batch["batch"], "count": len(batch["invoices"]),
            "lines": lines, "by_currency": dict(sorted(by_currency.items()))}


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        result = parse(json.load(f))
    with open(sys.argv[2], "w") as f:
        json.dump(result, f, sort_keys=True)
'''


# --------------------------------------------------------------------------
# CLI — each subcommand is one agent tool call
# --------------------------------------------------------------------------
def _fail(msg: str) -> None:
    print(f"ENGINE REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dyn_engine", description="DYNAMIS work-loop engine (dyn.engine.v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("job_new")
    p.add_argument("root"); p.add_argument("--job-id", required=True)
    p.add_argument("--entity", default="ent-001"); p.add_argument("--revenue-ref", default="env-ops-001")
    p.add_argument("--value-usds", type=int, default=500)
    p.add_argument("--deadline-day", type=int, default=10); p.add_argument("--day", type=int, default=1)
    p.add_argument("--seed", type=int, default=30161); p.add_argument("--count", type=int, default=500)

    p = sub.add_parser("work"); p.add_argument("root"); p.add_argument("artifact")
    p = sub.add_parser("check"); p.add_argument("root"); p.add_argument("--day", type=int, default=1)
    p = sub.add_parser("settle"); p.add_argument("root"); p.add_argument("--day", type=int, default=10)
    p = sub.add_parser("post"); p.add_argument("root"); p.add_argument("--day", type=int, default=10)
    p.add_argument("--post-id", default="post-demo-001")
    sub.add_parser("demo")

    a = ap.parse_args(argv)

    if a.cmd == "demo":
        return demo()

    loop = WorkLoop(a.root)
    if a.cmd == "job_new":
        job = loop.job_new(job_id=a.job_id, entity_id=a.entity, revenue_ref=a.revenue_ref,
                           value_muc=usds(a.value_usds), deadline_day=a.deadline_day,
                           seed=a.seed, count=a.count,
                           currencies=("USD", "EUR"), buyer_count=20, day=a.day)
        print(f"opened {job['job_id']} — class {job['verification_class']}, "
              f"escrow {job['escrow_usds_muc'] // 1_000_000} USDS, target in {a.root}/inputs/")
    elif a.cmd == "work":
        art = loop.work(a.artifact)
        print(f"artifact recorded: sha256 {art['sha256'][:16]}… ({art['bytes']} bytes)")
    elif a.cmd == "check":
        res = loop.check(day=a.day)
        print(f"check overall: {res['overall']} ({res['records']} evidence records, "
              f"{res['runtime_s']}s)")
    elif a.cmd == "settle":
        res = loop.settle(day=a.day)
        print(f"settled: payout {res['payout_muc'] // 1_000_000} USDS "
              f"(fee {res['fee_muc'] // 1_000_000}), emitted {res['emitted_dyn_mu']} DYN µ, "
              f"chain_ok={res['chain_ok']}")
    elif a.cmd == "post":
        wire = loop.post(day=a.day, post_id=a.post_id)
        print(f"posted {wire['post_id']} — {len(wire['embeds'])} verifiable embeds "
              f"-> {a.root}/post/preview.html")
    return 0


def demo() -> int:
    """The whole loop offline, on a real artifact: open → work → check → settle → post."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "invoice-batch-500"
        art = root / "invoice_parser.py"
        root.mkdir(parents=True)
        art.write_text(ARTIFACT_INVOICE_PARSER)
        for args in (["job_new", str(root), "--job-id", "job-demo-loop-1"],
                     ["work", str(root), str(art)],
                     ["check", str(root)],
                     ["settle", str(root)],
                     ["post", str(root)]):
            main(args)
        log = _read_json(root / "dyn-job.json")
        print("\nworklog history:")
        for h in log["history"]:
            print(f"  {h['seq']}. {h['kind']}: " + ", ".join(
                f"{k}={v}" for k, v in h.items() if k not in ("seq", "kind")))
        print(f"\nfinal status: {log['status']} — a folder any witness can re-check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
