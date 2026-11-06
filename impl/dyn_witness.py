#!/usr/bin/env python3
"""dyn.witness.v1 — the witness band: sampled re-execution that catches fraud.

Gate 2.3's acceptance line, executable in-repo: *class-C sampled re-execution
catches a seeded fraud*. The economics it closes: settlement re-reads evidence
verdicts from disk, so a worker who edits an evidence record and flips the
worklog status can make a failed build look paid-for. `forge_pass()` performs
exactly that attack (public, so anyone can reproduce it); the band closes it:

  - 7 witnesses; the leader for a job/day is picked by VRF order (stand-in:
    deterministic domain-hash ranking — real VRF-over-custody-score is gate
    2.1 hardening);
  - sampling is deterministic per (job, class, day) and scales with class:
    A 5% → E 100% (docs/01's verification stack: sampled re-execution is the
    default instrument above deterministic checks);
  - review copies the job folder into a sandbox, re-runs the *same* check
    harness on the hash-pinned artifact and inputs, and compares evidence
    digests — independence comes from fresh execution, not reimplementation;
  - a mismatch overrules: the engine's `witness_overrule` (the only PASS→FAIL
    path) reinstalls the re-executed truth, then the standard fail path
    refunds the escrow in full. Unsampled jobs stay catchable by anyone who
    re-runs `review` later — verification is re-runnable, not trusted.

  python3 dyn_witness.py demo          # forge, catch, refund — end to end

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_engine import (STATUS_FAIL, STATUS_PASS,  # noqa: E402
                        STATUS_WORKING, WorkLoop)
from dynamis_core.canonical import (domain_hash,  # noqa: E402
                                    object_hash)

WITNESS = "dyn.witness.v1"
WITNESSES = tuple(f"witness-{i}" for i in range(1, 8))   # 7 active, BFT ≤ 1
SAMPLE_RATES = {"A": 5, "B": 10, "C": 25, "D": 50, "E": 100}  # % of jobs
VRF_DOMAIN = "dyn.witness.vrf"
SAMPLE_DOMAIN = "dyn.witness.sample"


def leader_for(job_id: str, day: int,
               band: tuple[str, ...] = WITNESSES) -> str:
    """VRF stand-in: the witness whose hash ranks first for this job/day.
    Deterministic (anyone recomputes the same order), unpredictable in
    advance — the property sampling needs; real VRF signatures come with the
    HSM hardening."""
    return max(band, key=lambda w: int(
        domain_hash(VRF_DOMAIN, {"job": job_id, "day": day, "w": w})[:16], 16))


def sampled(job_id: str, cls: str, day: int) -> bool:
    """Deterministic per (job, class, day) — no one can pick which jobs to
    dodge, because the dice were cast before the artifact existed."""
    rate = SAMPLE_RATES[cls]
    return int(domain_hash(SAMPLE_DOMAIN,
                           {"job": job_id, "cls": cls, "day": day})[:8], 16) \
        % 100 < rate


DIGEST_FIELDS = ("n", "engine", "artifact_sha256", "check", "cls",
                 "verdict", "measured")


def evidence_digest(job_root: str | Path) -> str:
    """Canonical digest over the evidence a settlement would stand on.

    Projection is fixed and documented: the fields forgery touches (verdict,
    artifact hash, measured values) — and deliberately NOT the check `day` or
    the float instrument metadata (`confidence`, `runtime_s`, banned from
    canonical wire by ADR-0007): an honest re-execution on a later day must
    reproduce the digest, or every sampled job would flag as forged. A forger
    who edits a verdict still trips it; swapping the artifact changes
    artifact_sha256; there is no field a cheat can touch that the projection
    ignores and the settlement needs."""
    root = Path(job_root)
    loop = WorkLoop(root)
    records = [{k: r[k] for k in DIGEST_FIELDS if k in r}
               for r in (_read_json(root / rel)
                         for rel in loop.log["evidence"])]
    return object_hash(records)


def reexecute(job_root: str | Path, *,
              day: int | None = None) -> dict:
    """Fresh execution of the same harness in a sandbox: the proof, not a
    promise. The sandbox's status may need reinstating to WORKING when the
    folder reached a terminal state — the copy is throwaway, only the
    evidence it produces matters."""
    sandbox = Path(tempfile.mkdtemp(prefix="dyn-witness-"))
    durable = Path(tempfile.mkdtemp(prefix="dyn-witness-truth-"))
    try:
        copy = sandbox / Path(job_root).name
        shutil.copytree(job_root, copy)
        loop = WorkLoop(copy)
        if loop.log["status"] not in (STATUS_WORKING, STATUS_FAIL, STATUS_PASS):
            loop.log["status"] = STATUS_WORKING   # sandbox only; disk untouched
        res = loop.check(day=day or loop.log["job"]["deadline_day"])
        truth = durable / "evidence"
        shutil.copytree(copy / "evidence", truth)   # outlives the sandbox
        return {"overall": res["overall"],
                "digest": evidence_digest(copy),
                "evidence_dir": str(truth)}
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


CRAFT_DIGEST_FIELDS = ("check", "passed", "similarity_milli", "claims", "summary")
CRAFT_WITNESSES = 3


def craft_evidence_digest(check_result: dict) -> str:
    """Canonical digest over what a craft settlement stands on, the same
    projection rule as evidence_digest: the fields forgery touches and the
    settlement needs — the check id, the verdict, the likeness, every
    claim's title/passed/detail, the person's summary line — and deliberately
    NOT the round number, timestamps, runtime or the fixes brief (a later
    honest re-execution must reproduce the digest; ADR-0007 keeps floats off
    the canonical wire, so likeness rides as per-mille)."""
    r = check_result
    return object_hash({
        "check": r["check"], "passed": r["passed"],
        "similarity_milli": r.get("similarity_milli"),
        "claims": [{"title": c["title"], "passed": c["passed"],
                    "detail": c.get("detail", "")} for c in r["claims"]],
        "summary": r.get("summary", ""),
    })


def craft_reexecute(job_root: str | Path, *, day: int | None = None,
                    witnesses: int = CRAFT_WITNESSES) -> dict:
    """The verification game over a craft job, as the band runs it over an
    engine job: the leader (VRF stand-in) and the next witnesses each copy
    the job folder into a fresh sandbox, reinstate the status and re-run the
    SAME check harness — independence comes from fresh execution, not
    reimplemention. Deterministic harness, so the witnesses must agree; any
    disagreement between the re-executed truth and the delivered check is
    the forgery signal."""
    from dyn_craft import CraftJob          # lazy: dyn_craft imports agent_kit
    from dyn_ledger import WorkLedger
    root = Path(job_root)
    manifest = _read_json(root / "craft.json")
    leader_day = day or manifest["deadline_day"]
    band = (leader_for(manifest["job_id"], leader_day),)
    band += tuple(w for w in WITNESSES if w != band[0])[:max(1, witnesses) - 1]
    digests: list[str] = []
    for w in band:
        sandbox = Path(tempfile.mkdtemp(prefix="dyn-witness-craft-"))
        try:
            copy = sandbox / root.name
            shutil.copytree(root, copy)
            job = CraftJob(copy)
            if job.manifest["status"] not in ("built", "checked_fail"):
                job.manifest["status"] = "built"   # sandbox only; disk untouched
                job.manifest["step"] = "check"
            res = job.check(ledger=WorkLedger(), day=leader_day)
            digests.append(craft_evidence_digest(res))
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
    return {"leader": band[0], "band": list(band), "digests": digests,
            "agree": len(set(digests)) == 1}


def craft_verify(job_root: str | Path, *, day: int | None = None,
                 delivered_digest: str | None = None) -> dict:
    """The settle-time question: does a fresh re-execution reproduce the
    check the worker submits for settlement? The delivered digest must come
    from the submitter's own record (the caller passes it from memory); the
    re-executed truth is computed from the artifact on disk. A forger who
    edits either side trips the other."""
    root = Path(job_root)
    if delivered_digest is None:
        manifest = _read_json(root / "craft.json")
        delivered_digest = craft_evidence_digest(manifest["checks"][-1])
    game = craft_reexecute(job_root, day=day)
    truth = game["digests"][0]
    ok = game["agree"] and truth == delivered_digest
    return {"verified": ok, "delivered_digest": delivered_digest,
            "reexecuted_digest": truth, **game}


def forge_pass(job_root: str | Path) -> dict:
    """The seeded attack: edit evidence verdicts to PASS and flip the worklog
    status — what a cheating worker does before requesting settlement. This
    function is the fraud; the band is the answer."""
    loop = WorkLoop(job_root)
    changed = 0
    for rel in loop.log["evidence"]:
        p = Path(job_root) / rel
        rec = _read_json(p)
        if rec["verdict"] != "PASS":
            rec["verdict"] = "PASS"
            p.write_text(json.dumps(rec, sort_keys=True, indent=1))
            changed += 1
    loop.log["status"] = STATUS_PASS
    loop._save()
    return {"forged_records": changed, "status": loop.log["status"]}


def review(job_root: str | Path, *, day: int, cls: str,
           force_sample: bool = False) -> dict:
    """The band's verdict on one job. `matches` is None when not sampled —
    the honest answer 'not checked this time', not a rubber stamp."""
    root = Path(job_root)
    led = leader_for(root.name, day)
    is_sampled = force_sample or sampled(root.name, cls, day)
    out = {"witness": WITNESS, "job": root.name, "leader": led,
           "cls": cls, "day": day, "sampled": is_sampled,
           "original_digest": evidence_digest(root),
           "reexec_digest": None, "reexec_overall": None,
           "matches": None, "forged": False}
    if not is_sampled:
        return out
    rx = reexecute(root, day=day)
    loop = WorkLoop(root)
    out["reexec_digest"] = rx["digest"]
    out["reexec_overall"] = rx["overall"]
    # "matches" means: the evidence reproduces. An honest FAIL re-executes to
    # the same FAIL digest — that evidence is true, and the normal fail path
    # handles it. Only a digest mismatch is forgery.
    out["matches"] = rx["digest"] == out["original_digest"]
    out["forged"] = not out["matches"]
    if not out["matches"]:
        # the only PASS→FAIL path, and it carries the re-executed proof
        loop.witness_overrule(day=day, true_evidence_dir=rx["evidence_dir"],
                              leader=led)
        out["overruled"] = True
    shutil.rmtree(Path(rx["evidence_dir"]).parent, ignore_errors=True)
    return out


def resolve(job_root: str | Path, *, day: int, cls: str, worker_id: str,
            force_sample: bool = False) -> dict:
    """Sample, verify, and route: forged → refund in full; anything else →
    proceed (the caller settles on PASS or refunds on FAIL as usual).
    No settlement stands on evidence the band cannot reproduce."""
    root = Path(job_root)
    v = review(root, day=day, cls=cls, force_sample=force_sample)
    if v["matches"] is False:
        loop = WorkLoop(root)
        back = loop.refund(day=day, worker_id=worker_id)
        v["action"] = "refund"
        v["refund"] = back
    else:
        v["action"] = "proceed"
    return v


# --------------------------------------------------------------------------
def demo() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dyn-witness-demo-"))
    from dyn_engine import ARTIFACT_INVOICE_PARSER
    root = tmp / "job-forged-001"
    loop = WorkLoop(root)
    loop.job_new(job_id="job-forged-001", entity_id="ent-001",
                 revenue_ref="env-ops-001", value_muc=500_000_000,
                 deadline_day=9, seed=30161, count=500,
                 currencies=("USD", "EUR"), buyer_count=20, day=1)
    art = root / "incoming.py"
    art.write_text(ARTIFACT_INVOICE_PARSER.replace(
        '+ ln["qty"] * ln["unit_cents"]',
        '+ ln["qty"] * ln["unit_cents"] + 1'))
    loop.work(art)
    loop.check(day=1)
    print(f"{WITNESS} — the seeded fraud, caught")
    print(f"  real check: {loop.log['status']} (the build is wrong)")
    f = forge_pass(root)
    print(f"  worker forges: {f['forged_records']} evidence records edited "
          f"→ status {f['status']}")
    v = resolve(root, day=2, cls="E", worker_id="agent-fraud-1",
                force_sample=True)
    print(f"  band review: leader {v['leader']}, sampled (class E = 100%), "
          f"re-executed → {v['reexec_overall']}, digests differ: "
          f"{v['original_digest'][:12]}… vs {v['reexec_digest'][:12]}…")
    r = v["refund"]
    print(f"  verdict: forged → refund in full: {r['escrow_back_muc']:,} µ¢ "
          f"back, fee 0, emission 0")
    print("  the machine never pays — gate 2.3's acceptance line, in-repo.")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dyn_witness", description="DYNAMIS witness band (dyn.witness.v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    a = ap.parse_args(argv)
    return demo()


def _read_json(p: Path) -> dict:
    return json.loads(Path(p).read_text())


if __name__ == "__main__":
    raise SystemExit(main())
