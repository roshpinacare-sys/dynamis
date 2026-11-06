#!/usr/bin/env python3
"""dyn.app.v1 — the DYNAMIS network as one running application.

The ask was a running network, not a protocol spec. The protocol packages exist
and are tested; what was missing is the product surface that makes them one
thing a person can open and use. This module is that thing: a single stdlib
server (ADR-0007) that runs the real loops as one live network — identity
(Law 3/17/18 passports), the work loop with real escrow (dyn.engine.v1 —
submitted artifacts are executed and checked for real, settlement is
fail-closed on evidence), the artifact-only social rail (dyn.social.v1 —
Law 13 enforced on every publish), the shared compute pool (dyn.compute.v1 —
real benchmark receipts, best-fit anti-herd allocation, ERG settlement), and
the hash-chained work ledger whose Law-19 invariant is recomputed from the
app's own actions.

  python3 impl/dyn_app.py serve --port 8800 --state /tmp/dyn-state

Then open http://127.0.0.1:8800/ — the operating console. Every button is a
real protocol action; every number is recomputed from live state, not prose.

Named limitations, on the record: signatures are HSM stand-ins until real
keyrefs issue (docs/10); the compute price round samples the reference band
until three external witnesses are live (gate 3.1); rail/pool state is
per-process (the chain of record for money is the emission escrow inside
dyn.engine.settle, which is durable on disk).

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_compute import Pool, ComputeError  # noqa: E402
from dyn_craft import CraftJob, CraftError, dispute_on_record  # noqa: E402
from dyn_bench import run_benchmark  # noqa: E402
from dyn_engine import ARTIFACT_INVOICE_PARSER, EngineError, WorkLoop  # noqa: E402
from dyn_ledger import WorkLedger, verify_checkpoint  # noqa: E402
from dyn_post import PostValueError, from_wire, parse_post, render_post, \
    to_wire, validate_limits  # noqa: E402
from dyn_social import Rail, SocialError, signature_stand_in  # noqa: E402
from dynamis_core.canonical import object_hash, usds  # noqa: E402
from dynamis_core.objects import AgentPassport  # noqa: E402
from dynamis_core.pricefeed import collect_round  # noqa: E402

APP = "dyn.app.v1"
ROOT = Path(__file__).resolve().parent.parent
UI_PATH = ROOT / "app" / "index.html"
CAPABILITIES = ("social.post", "job.claim", "job.post", "compute.hire", "dm.send")
STARTER_STAKE_DYN_MU = 2_500_000
# the custody peg for auction stakes: 1 DYN µ of stake ↔ 1 µ¢ held — a
# documented stand-in for a market price, like the VRF stand-in for a VRF
STAKE_PEG_MUC_PER_MU = 1
# the reference price band (µ¢ per ERG) — three reference witnesses until 3.1
REFERENCE_SAMPLES = {"w-reference-1": 2200, "w-reference-2": 2400,
                     "w-reference-3": 2600}


class AppError(ValueError):
    pass


class Dynamis:
    """One running network. Every mutation is a protocol action on record."""

    def __init__(self, *, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        (self.state_root / "jobs").mkdir(parents=True, exist_ok=True)
        (self.state_root / "inbox").mkdir(parents=True, exist_ok=True)
        self.day = 1
        self.rail = Rail()
        self.pool = Pool()
        # the chain's seals, kept as the events happen — the anchor an
        # observer holds so a rewritten past has something to contradict
        self.checkpoints: list[dict] = []
        self.ledger = WorkLedger(seal_hook=self._store_seal)
        self.lock = threading.RLock()
        self.agents: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.craft: dict[str, dict] = {}
        (self.state_root / "craft").mkdir(parents=True, exist_ok=True)
        self.price_round = None
        self._post_seq = 0
        self._job_seq = 0
        self._craft_seq = 0
        self.totals = {"jobs_settled": 0, "jobs_refunded": 0, "payout_muc": 0,
                       "fee_muc": 0, "emitted_dyn_mu": 0, "escrow_back_muc": 0,
                       "compute_cost_muc": 0, "craft_settled_muc": 0}

    # ---------- identity (pillar 1) ----------
    def join(self, agent_id: str, persona: str) -> dict:
        with self.lock:
            if agent_id in self.agents:
                raise AppError(f"{agent_id} already holds a passport")
            passport = AgentPassport(
                agent_id=agent_id, persona=persona,
                keyrefs=(f"hsm:kr-{agent_id}",), capabilities=CAPABILITIES,
                wallet=f"pw-{agent_id}", census_day=self.day)
            self.rail.open_account(passport, day=self.day)
            rec = {"agent_id": agent_id, "persona": persona,
                   "keyref": f"hsm:kr-{agent_id}", "wallet": f"pw-{agent_id}",
                   "capabilities": list(CAPABILITIES),
                   "joined_day": self.day, "balance_muc": 0,
                   "earned_muc": 0, "stake_dyn_mu": STARTER_STAKE_DYN_MU,
                   "stakes": {}}
            self.agents[agent_id] = rec
            return dict(rec)

    # ---------- the work loop (pillar 3) ----------
    def open_job(self, *, buyer: str, value_usds: int = 500, count: int = 500,
                 seed: int | None = None) -> dict:
        with self.lock:
            if buyer not in self.agents:
                raise AppError(f"buyer {buyer} has no passport — join first")
            self._job_seq += 1
            job_id = f"job-{self._job_seq:04d}"
            root = self.state_root / "jobs" / job_id
            loop = WorkLoop(root)
            job = loop.job_new(
                job_id=job_id, entity_id="ent-001",
                revenue_ref=f"env-{job_id}", value_muc=usds(value_usds),
                deadline_day=self.day + 10, seed=seed if seed is not None else 30161,
                count=count, currencies=("USD", "EUR"), buyer_count=20,
                day=self.day)
            self.jobs[job_id] = {"loop": loop, "root": root, "buyer": buyer,
                                 "worker": None}
            self.ledger.append(day=self.day, kind="open", job_id=job_id,
                               agent=buyer,
                               escrow_usds_muc=job["escrow_usds_muc"],
                               verification_class=job["verification_class"])
            return self.job_view(job_id)

    def submit_artifact(self, job_id: str, code: str, worker: str) -> dict:
        with self.lock:
            job = self._job(job_id)
            if worker not in self.agents:
                raise AppError(f"worker {worker} has no passport")
            if job["worker"] is None:
                job["worker"] = worker
            inbox = self.state_root / "inbox" / f"{job_id}.py"
            inbox.write_text(code, encoding="utf-8")
            art = job["loop"].work(inbox)
            self.ledger.append(day=self.day, kind="work", job_id=job_id,
                               agent=worker, sha256=art["sha256"],
                               bytes=art["bytes"])
            inbox.unlink()
            return dict(art)

    def check_job(self, job_id: str) -> dict:
        with self.lock:
            job = self._job(job_id)
            res = job["loop"].check(day=self.day)
            self.ledger.append(day=self.day, kind="check", job_id=job_id,
                               agent=self._worker_of(job_id),
                               overall=res["overall"], records=res["records"])
            return res

    def settle_job(self, job_id: str) -> dict:
        with self.lock:
            job = self._job(job_id)
            worker = self._worker_of(job_id)
            rec = self.agents[worker]
            result = job["loop"].settle(
                day=self.day, worker_id=worker,
                persona=rec["persona"], keyref=rec["keyref"])
            self.ledger.append(day=self.day, kind="settle", job_id=job_id,
                               agent=worker, payout_muc=result["payout_muc"],
                               fee_muc=result["fee_muc"],
                               emitted_dyn_mu=result["emitted_dyn_mu"])
            self.totals["jobs_settled"] += 1
            self.totals["payout_muc"] += result["payout_muc"]
            self.totals["fee_muc"] += result["fee_muc"]
            self.totals["emitted_dyn_mu"] += result["emitted_dyn_mu"]
            rec["earned_muc"] += result["payout_muc"]
            rec["balance_muc"] += result["payout_muc"]
            return result

    def refund_job(self, job_id: str) -> dict:
        with self.lock:
            self._job(job_id)
            result = self.jobs[job_id]["loop"].refund(day=self.day)
            self.ledger.append(day=self.day, kind="refund", job_id=job_id,
                               agent=self._worker_of(job_id),
                               escrow_back_muc=result["escrow_back_muc"],
                               emitted_dyn_mu=0)
            self.totals["jobs_refunded"] += 1
            self.totals["escrow_back_muc"] += result["escrow_back_muc"]
            return result

    def job_view(self, job_id: str) -> dict:
        with self.lock:
            loop = self._job(job_id)["loop"]
            log = loop.log
            return {"job_id": job_id, "status": log["status"],
                    "buyer": self.jobs[job_id]["buyer"],
                    "worker": self.jobs[job_id]["worker"],
                    "escrow_usds_muc": log["job"]["escrow_usds_muc"],
                    "verification_class": log["job"]["verification_class"],
                    "count": log["job"]["spec"]["count"],
                    "artifact": log["artifact"],
                    "evidence": log["evidence"], "history": log["history"],
                    "post": log["post"]}

    def _job(self, job_id: str) -> dict:
        if job_id not in self.jobs:
            raise AppError(f"no such job: {job_id}")
        return self.jobs[job_id]

    def _worker_of(self, job_id: str) -> str:
        worker = self.jobs[job_id]["worker"]
        if worker is None:
            raise AppError(f"{job_id} has no worker yet")
        return worker

    # ---------- the social rail (pillar 2 + pillar 5) ----------
    def publish(self, author: str, source: str) -> dict:
        with self.lock:
            if author not in self.agents:
                raise AppError(f"author {author} has no passport")
            post = parse_post(source)
            validate_limits(post)
            self._post_seq += 1
            wire = to_wire(post, post_id=f"post-{self.day:02d}-{self._post_seq:03d}",
                           author=author, day=self.day)
            post_id = self.rail.publish(author, wire, day=self.day)
            self.ledger.append(day=self.day, kind="post", job_id="-",
                               agent=author, post_id=post_id,
                               embeds=len(wire["embeds"]))
            return {"post_id": post_id, "embeds": len(wire["embeds"]),
                    "wire": wire, "html": render_post(post)}

    def feed(self, reader: str) -> dict:
        with self.lock:
            rows = self.rail.feed(reader, day=self.day)
            rendered = [{"post_id": r["post_id"], "author": r["author"],
                         "wire": self.rail.posts[r["post_id"]],
                         "html": render_post(
                             from_wire(self.rail.posts[r["post_id"]]))}
                        for r in rows]
            return {"featured": self.rail.feature_daily(day=self.day),
                    "posts": rendered}

    def follow(self, actor: str, target: str) -> dict:
        with self.lock:
            self.rail.follow(actor, target, day=self.day)
            return {"following": self.rail.following[actor]}

    def send_dm(self, sender: str, recipient: str, body: str) -> dict:
        with self.lock:
            self.rail.send_dm(sender, recipient, day=self.day, body=body,
                              sig=signature_stand_in(sender, self.day,
                                                     f"dm:{recipient}:{body}"))
            return {"sent": True}

    def inbox(self, reader: str) -> list[dict]:
        with self.lock:
            return self.rail.read_inbox(
                reader, day=self.day,
                sig=signature_stand_in(reader, self.day, f"inbox:{reader}"))

    # ---------- the compute pool (pillar 4) ----------
    def register_device(self, device_id: str) -> dict:
        with self.lock:
            receipt = run_benchmark(device_id, day=self.day)   # a REAL measurement
            self.pool.register_device(device_id, receipt, day=self.day)
            return {"device_id": device_id, "tier": receipt["tier"],
                    "throughput_us": receipt["throughput_us"],
                    "receipt_digest": receipt["receipt_digest"]}

    def set_reference_price(self) -> dict:
        with self.lock:
            rnd = collect_round(self.day, dict(REFERENCE_SAMPLES))
            self.pool.set_price_round(rnd, day=self.day)
            self.price_round = rnd
            return {"median_muc": rnd.median_muc, "accepted": rnd.accepted,
                    "note": "reference band — live witness sampling is gate 3.1"}

    def post_compute_job(self, job_id: str, requester: str, erg_milli: int,
                         tier_min: str = "T1") -> dict:
        with self.lock:
            if requester not in self.agents:
                raise AppError(f"requester {requester} has no passport")
            return self.pool.post_job(job_id, requester, day=self.day,
                                      erg_milli=erg_milli, tier_min=tier_min)

    def allocate_compute(self) -> dict:
        with self.lock:
            return self.pool.allocate(day=self.day)

    def settle_compute(self, job_id: str) -> dict:
        with self.lock:
            result = self.pool.settle(job_id, day=self.day)
            self.totals["compute_cost_muc"] += result["cost_muc"]
            return result

    def compute_state(self) -> dict:
        with self.lock:
            devices = [{"device_id": d.device_id, "tier": d.tier,
                        "throughput_us": d.throughput_us,
                        "scheduled_today": d.scheduled_today}
                       for d in self.pool.devices.values()]
            return {"devices": devices,
                    "jobs": {jid: j["state"] for jid, j in self.pool.jobs.items()},
                    "price_median_muc": self.price_round.median_muc
                    if self.price_round else None,
                    "ledger": self.pool.ledger.verify_chain(),
                    "refusals": len(self.pool.ledger.refusals())}

    # ---------- the craft loop (dyn.craft.v1 — study → build → check → ready) ----------
    def open_craft(self, *, buyer: str, request: str, target_kind: str,
                   target_ref: str, value_usds: int = 500,
                   good_enough: float | None = None) -> dict:
        with self.lock:
            if buyer not in self.agents:
                raise AppError(f"buyer {buyer} has no passport — join first")
            self._craft_seq += 1
            job_id = f"craft-{self._craft_seq:04d}"
            root = self.state_root / "craft" / job_id
            job = CraftJob(root)
            kwargs = {"good_enough": good_enough} if good_enough is not None else {}
            job.open(job_id=job_id, buyer=buyer, request=request,
                     target_kind=target_kind, target_ref=target_ref,
                     value_usds=value_usds, ledger=self.ledger,
                     day=self.day, **kwargs)
            self.craft[job_id] = {"job": job, "root": root}
            return dict(job.manifest)

    def _craft(self, job_id: str) -> CraftJob:
        if job_id not in self.craft:
            raise AppError(f"no such craft job: {job_id}")
        return self.craft[job_id]["job"]

    def craft_study(self, job_id: str) -> dict:
        with self.lock:
            return self._craft(job_id).study(ledger=self.ledger, day=self.day)

    def craft_build(self, job_id: str, worker: str, files: dict[str, str],
                    statement: str | None = None) -> dict:
        with self.lock:
            if worker not in self.agents:
                raise AppError(f"worker {worker} has no passport")
            ban = dispute_on_record(self.ledger, worker,
                                    keyref=self.agents[worker]["keyref"])
            if ban:
                raise AppError(f"worker {worker} is banned (dispute on job {ban})")
            return self._craft(job_id).build(worker=worker, files=files,
                                             ledger=self.ledger, day=self.day,
                                             statement=statement)

    def craft_bid_route(self, job_id: str, body: dict) -> dict:
        """A worker applies to build: terms on the record while the buyer
        decides; the award binds and only the awarded worker builds. The
        stake is custody, not a number: it is held from the bidder's rail
        balance at the documented peg (1 DYN µ ↔ 1 µ¢ — a stand-in for a
        market price, like the VRF stand-in for a VRF). You bid with what
        you've earned; a fresh passport cannot outbid with figures."""
        with self.lock:
            worker = body.get("worker", "")
            if worker not in self.agents:
                raise AppError(f"worker {worker} has no passport")
            rec = self.agents[worker]
            stake = int(body.get("stake_dyn_mu", 0))
            ban = dispute_on_record(self.ledger, worker, keyref=rec["keyref"])
            if ban:
                raise AppError(f"worker {worker} is banned (dispute on job {ban})")
            if stake * STAKE_PEG_MUC_PER_MU > rec["balance_muc"]:
                raise AppError(
                    f"bid with what you've earned — {worker} holds "
                    f"{rec['balance_muc']:,} µ¢, the stake asks "
                    f"{stake:,} µ¢ at the peg")
            out = self._craft(job_id).bid(
                worker=worker, price_usds_muc=int(body.get("price_usds_muc", 0)),
                stake_dyn_mu=stake, ledger=self.ledger, day=self.day)
            rec["balance_muc"] -= stake * STAKE_PEG_MUC_PER_MU
            rec["stakes"][job_id] = rec.get("stakes", {}).get(job_id, 0) + stake
            self.ledger.append(day=self.day, kind="stake", job_id=job_id,
                               agent=worker, action="hold", amount_muc=stake,
                               balance_muc=rec["balance_muc"])
            out["custody"] = {"held_muc": stake * STAKE_PEG_MUC_PER_MU,
                              "balance_muc": rec["balance_muc"]}
            return out

    def craft_check(self, job_id: str) -> dict:
        with self.lock:
            return self._craft(job_id).check(ledger=self.ledger, day=self.day)

    def craft_settle(self, job_id: str) -> dict:
        with self.lock:
            job = self._craft(job_id)
            worker = job.manifest.get("worker")
            if worker not in self.agents:
                raise AppError(f"worker {worker} has no passport")
            rec = self.agents[worker]
            result = job.settle(ledger=self.ledger, day=self.day,
                                persona=rec["persona"], keyref=rec["keyref"])
            self.totals["craft_settled_muc"] += result["payout_muc"]
            rec["earned_muc"] += result["payout_muc"]
            rec["balance_muc"] += result["payout_muc"]
            held = rec.get("stakes", {}).pop(job_id, 0)
            if held:
                if result["verdict"] == "paid":
                    rec["balance_muc"] += held * STAKE_PEG_MUC_PER_MU
                    action = "return"
                else:
                    action = "burn"      # a lost dispute forfeits the stake
                self.ledger.append(day=self.day, kind="stake", job_id=job_id,
                                   agent=worker, action=action, amount_muc=held,
                                   balance_muc=rec["balance_muc"])
            # the auction is over: every losing bidder gets its stake back
            for w, other in self.agents.items():
                if w == worker:
                    continue
                lost = other.get("stakes", {}).pop(job_id, 0)
                if lost:
                    other["balance_muc"] += lost * STAKE_PEG_MUC_PER_MU
                    self.ledger.append(day=self.day, kind="stake", job_id=job_id,
                                       agent=w, action="return", amount_muc=lost,
                                       balance_muc=other["balance_muc"])
            return result

    def craft_verify_route(self, job_id: str) -> dict:
        """Anyone can re-run the verification game, read-only — verification
        is re-runnable, not trusted. No money moves here."""
        with self.lock:
            job = self._craft(job_id)
            m = job.manifest
            if not m.get("checks"):
                raise AppError("no check on the record to verify")
            from dyn_witness import craft_evidence_digest
            from dyn_witness import craft_verify as run_game
            out = run_game(job.root, day=self.day,
                           delivered_digest=craft_evidence_digest(m["checks"][-1]))
            out["job_id"] = m["job_id"]
            out["status"] = m["status"]
            return out

    def craft_refund(self, job_id: str) -> dict:
        with self.lock:
            result = self._craft(job_id).refund(ledger=self.ledger, day=self.day)
            self.totals["escrow_back_muc"] += result["escrow_back_muc"]
            # every bidder gets their stake back — deny comes before any award
            for w, rec in self.agents.items():
                held = rec.get("stakes", {}).pop(job_id, 0)
                if held:
                    rec["balance_muc"] += held * STAKE_PEG_MUC_PER_MU
                    self.ledger.append(day=self.day, kind="stake", job_id=job_id,
                                       agent=w, action="return", amount_muc=held,
                                       balance_muc=rec["balance_muc"])
            return result

    def craft_answer(self, job_id: str, qid: str, answer: str, by: str | None) -> dict:
        with self.lock:
            if by and by not in self.agents:
                raise AppError(f"{by} has no passport — join first")
            return self._craft(job_id).answer(qid, answer, by=by,
                                              ledger=self.ledger, day=self.day)

    def craft_post(self, job_id: str) -> dict:
        with self.lock:
            return self._craft(job_id).post(day=self.day)

    def craft_view(self, job_id: str) -> dict:
        with self.lock:
            return dict(self._craft(job_id).manifest)

    def craft_list(self) -> dict:
        with self.lock:
            return {"jobs": [dict(self.craft[j]["job"].manifest) for j in self.craft]}

    def _store_seal(self, cp: dict) -> None:
        if cp:
            self.checkpoints.append(cp)

    def craft_audit(self) -> dict:
        """The observer's route: chain, invariant, and every seal — fail
        closed. A past that was sealed cannot be re-mined without the seals
        the observer already holds disagreeing; a missing or stale seal is
        a finding, not a pass."""
        with self.lock:
            problems: list[str] = []
            chain = self.ledger.verify_chain()
            if not chain["ok"]:
                problems.append(f"chain broken at seq {chain['first_bad']}")
            expected = self.ledger.all_checkpoints(day=self.day)
            stored = {cp["height"]: cp for cp in self.checkpoints}
            for cp in expected:
                h = cp["height"]
                if h not in stored:
                    problems.append(f"missing seal for height {h}")
                    continue
                v = verify_checkpoint(stored[h], self.ledger)
                if not v["ok"]:
                    problems.append(f"seal {h}: {v['why']}")
            extra = sorted(set(stored) - {cp["height"] for cp in expected})
            if extra:
                problems.append(f"stale seals beyond full windows: {extra}")
            inv = self.ledger.invariant()
            if not inv["emitted_eq_revenue"] or not inv["refund_emits_nothing"]:
                problems.append("emission invariant broken")
            return {"ok": not problems, "problems": problems, "chain": chain,
                    "invariant": inv, "seals": len(self.checkpoints),
                    "entries": len(self.ledger.entries)}

    # ---------- the chain (the record of all of it) ----------
    def chain(self) -> dict:
        with self.lock:
            return {"verify": self.ledger.verify_chain(),
                    "invariant": self.ledger.invariant(),
                    "entries": len(self.ledger.entries),
                    "rail_ledger": self.rail.ledger.verify_chain(),
                    "rail_refusals": len(self.rail.ledger.refusals())}

    def state(self) -> dict:
        with self.lock:
            statuses: dict[str, int] = {}
            for jid in self.jobs:
                st = self.jobs[jid]["loop"].log["status"]
                statuses[st] = statuses.get(st, 0) + 1
            return {"protocol": APP, "day": self.day,
                    "agents": len(self.agents), "jobs": len(self.jobs),
                    "job_statuses": statuses, "totals": dict(self.totals),
                    "chain": {"ok": self.ledger.verify_chain()["ok"],
                              "entries": len(self.ledger.entries)},
                    "rail": {"accounts": len(self.rail.accounts),
                             "ledger_ok": self.rail.ledger.verify_chain()["ok"]},
                    "compute": {"devices": len(self.pool.devices),
                                "jobs": len(self.pool.jobs)},
                    "craft": {"jobs": len(self.craft),
                              "settled_muc": self.totals["craft_settled_muc"]}}


# --------------------------------------------------------------------------
# the HTTP surface
# --------------------------------------------------------------------------
ROUTES_GET = ("/", "/health", "/api/state", "/api/agents", "/api/jobs",
              "/api/feed", "/api/chain", "/api/compute", "/api/craft",
              "/api/audit")
ROUTES_POST = ("/api/agents", "/api/jobs", "/api/posts", "/api/follow",
               "/api/dm", "/api/inbox", "/api/compute/devices",
               "/api/compute/price", "/api/compute/jobs",
               "/api/compute/allocate", "/api/compute/settle", "/api/craft")
JOB_ACTION_RE = re.compile(r"^/api/jobs/([a-z0-9-]+)/(artifact|check|settle|refund)$")
CRAFT_ACTION_RE = re.compile(
    r"^/api/craft/([a-z0-9-]+)/(study|build|check|settle|refund|post|answer|verify|bid)$")


def make_handler(net: Dynamis):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, body: dict | str, ctype: str) -> None:
            raw = body.encode() if isinstance(body, str) else \
                json.dumps(body, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, obj, "application/json")

        def _err(self, code: int, exc: Exception) -> None:
            self._json(code, {"error": str(exc)})

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(n))
            except json.JSONDecodeError as exc:
                raise AppError(f"bad JSON body: {exc}")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            try:
                if path == "/":
                    return self._send(200, UI_PATH.read_text(encoding="utf-8"),
                                      "text/html; charset=utf-8")
                if path == "/health":
                    return self._json(200, {"ok": True, "protocol": APP})
                if path == "/api/state":
                    return self._json(200, net.state())
                if path == "/api/agents":
                    return self._json(200, {"agents": list(net.agents.values())})
                if path == "/api/jobs":
                    return self._json(200, {"jobs": [net.job_view(j)
                                                     for j in net.jobs]})
                if path == "/api/feed":
                    reader = (urllib.parse.parse_qs(
                        urllib.parse.urlparse(self.path).query)
                        .get("reader", [""])[0])
                    if reader not in net.agents:
                        raise AppError("feed reader must hold a passport")
                    return self._json(200, net.feed(reader))
                if path == "/api/chain":
                    return self._json(200, net.chain())
                if path == "/api/audit":
                    return self._json(200, net.craft_audit())
                if path == "/api/compute":
                    return self._json(200, net.compute_state())
                if path == "/api/craft":
                    return self._json(200, net.craft_list())
                m = JOB_ACTION_RE.match(path)
                if m:
                    return self._json(200, net.job_view(m.group(1)))
                m = CRAFT_ACTION_RE.match(path)
                if m:
                    return self._json(200, net.craft_view(m.group(1)))
                return self._json(404, {"error": f"no route: {path}"})
            except (AppError, SocialError, ComputeError, EngineError,
                    PostValueError, ValueError) as exc:
                return self._err(400, exc)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            try:
                body = self._body()
                if path == "/api/agents":
                    return self._json(200, net.join(body["agent_id"],
                                                    body.get("persona",
                                                             body["agent_id"])))
                if path == "/api/jobs":
                    return self._json(200, net.open_job(buyer=body["buyer"],
                                                        value_usds=body.get("value_usds", 500),
                                                        count=body.get("count", 500),
                                                        seed=body.get("seed")))
                m = JOB_ACTION_RE.match(path)
                if m:
                    job_id, action = m.groups()
                    if action == "artifact":
                        return self._json(200, net.submit_artifact(
                            job_id, body["code"], body["worker"]))
                    if action == "check":
                        return self._json(200, net.check_job(job_id))
                    if action == "settle":
                        return self._json(200, net.settle_job(job_id))
                    return self._json(200, net.refund_job(job_id))
                m = CRAFT_ACTION_RE.match(path)
                if m:
                    job_id, action = m.groups()
                    if action == "study":
                        return self._json(200, net.craft_study(job_id))
                    if action == "build":
                        return self._json(200, net.craft_build(
                            job_id, body["worker"], body["files"]))
                    if action == "check":
                        return self._json(200, net.craft_check(job_id))
                    if action == "settle":
                        return self._json(200, net.craft_settle(job_id))
                    if action == "verify":
                        return self._json(200, net.craft_verify_route(job_id))
                    if action == "bid":
                        return self._json(200, net.craft_bid_route(job_id, body))
                    if action == "post":
                        return self._json(200, net.craft_post(job_id))
                    if action == "answer":
                        return self._json(200, net.craft_answer(
                            job_id, body["qid"], body["answer"], body.get("by")))
                    return self._json(200, net.craft_refund(job_id))
                if path == "/api/craft":
                    return self._json(200, net.open_craft(
                        buyer=body["buyer"], request=body["request"],
                        target_kind=body["target_kind"],
                        target_ref=body["target_ref"],
                        value_usds=body.get("value_usds", 500),
                        good_enough=body.get("good_enough")))
                if path == "/api/posts":
                    return self._json(200, net.publish(body["author"],
                                                       body["source"]))
                if path == "/api/follow":
                    return self._json(200, net.follow(body["actor"],
                                                      body["target"]))
                if path == "/api/dm":
                    return self._json(200, net.send_dm(body["sender"],
                                                       body["recipient"],
                                                       body["body"]))
                if path == "/api/inbox":
                    return self._json(200, {"inbox": net.inbox(body["reader"])})
                if path == "/api/compute/devices":
                    return self._json(200, net.register_device(body["device_id"]))
                if path == "/api/compute/price":
                    return self._json(200, net.set_reference_price())
                if path == "/api/compute/jobs":
                    return self._json(200, net.post_compute_job(
                        body["job_id"], body["requester"],
                        body["erg_milli"], body.get("tier_min", "T1")))
                if path == "/api/compute/allocate":
                    return self._json(200, net.allocate_compute())
                if path == "/api/compute/settle":
                    return self._json(200, net.settle_compute(body["job_id"]))
                if path in ROUTES_GET:
                    return self._err(405, Exception(f"{path} is read-only — GET only"))
                return self._json(404, {"error": f"no route: {path}"})
            except (AppError, SocialError, ComputeError, EngineError,
                    PostValueError, ValueError, KeyError) as exc:
                return self._err(400, exc)

        def do_PUT(self) -> None:  # noqa: N802
            self._send(405, {"error": "PUT refused — only GET and POST exist"},
                       "application/json")

        do_DELETE = do_PUT
        do_PATCH = do_PUT

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dyn_app", description="dyn.app.v1 — the DYNAMIS network application")
    ap.add_argument("cmd", choices=["serve"])
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--state", default=str(ROOT / "app" / "state"))
    ns = ap.parse_args(argv)
    net = Dynamis(state_root=ns.state)
    httpd = ThreadingHTTPServer((ns.host, ns.port), make_handler(net))
    print(f"{APP} — the network is live on http://{ns.host}:{ns.port}/ "
          f"(state: {ns.state}); Ctrl-C exits")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
