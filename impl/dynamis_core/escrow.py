"""The escrow job state machine (specs/state-machines.md is the formal spec; this is
the executable half). Fail-closed: any transition not listed here raises.

Money is µ¢ (integer). Fee: escrow.coordination_fee_bps = 500 (genesis), taken from
the escrow on settle; the remainder goes to the worker's PowerAccount. Every accepted
transition appends a hash-chained event — the fleet-economy pattern — so the machine's
history is verifiable by re-deriving the chain (Law 4: measured, or it did not happen).
"""
from __future__ import annotations

from .canonical import bps_of, object_hash

COORDINATION_FEE_BPS = 500  # params/genesis.yaml#escrow

TRANSITIONS: dict[tuple[str, str], str] = {
    ("OPEN", "fund"): "FUNDED",
    ("OPEN", "cancel"): "REFUNDED",
    ("FUNDED", "claim"): "CLAIMED",
    ("FUNDED", "timeout"): "REFUNDED",
    ("FUNDED", "cancel"): "REFUNDED",
    ("CLAIMED", "deliver"): "DELIVERED",
    ("CLAIMED", "timeout"): "REFUNDED",
    ("DELIVERED", "start_verify"): "VERIFYING",
    ("DELIVERED", "dispute"): "DISPUTED",
    ("DELIVERED", "timeout"): "REFUNDED",   # verifier stall must not trap worker funds
    ("VERIFYING", "dispute"): "DISPUTED",   # a challenger may join mid-verification
    ("VERIFYING", "verify_pass"): "SETTLED",
    ("VERIFYING", "verify_fail"): "DISPUTED",
    ("VERIFYING", "timeout"): "REFUNDED",
    ("DISPUTED", "resolve_worker"): "SETTLED",
    ("DISPUTED", "resolve_budget"): "REFUNDED",
}

# Refund paths return the full escrow; settle paths pay fee + worker.
TERMINAL = ("SETTLED", "REFUNDED")


class EscrowError(Exception):
    """Any illegal transition, guard failure, or chain violation."""


class JobMachine:
    """One escrowed job. `now_day` advances via tick(); deadlines enforce themselves."""

    def __init__(self, job, funded_by: str = "") -> None:
        self.job = job
        self.state: str = "OPEN"
        self.funded_by = funded_by
        self.claim = None
        self.now_day: int = 1
        self.worker_payout_muc: int = 0
        self.fee_muc: int = 0
        self._events: list[dict] = []
        self._append("open", {"state": self.state, "class": job.verification_class})

    # -- event chain ----------------------------------------------------------
    def _append(self, kind: str, body: dict) -> str:
        prev = self._events[-1]["hash"] if self._events else "0" * 64
        ev = {"seq": len(self._events), "day": self.now_day, "kind": kind,
              "prev": prev, "body": body}
        ev["hash"] = object_hash({"prev": prev, "seq": ev["seq"], "kind": kind,
                                  "day": ev["day"], "body": body})
        self._events.append(ev)
        return ev["hash"]

    @property
    def events(self) -> tuple[dict, ...]:
        return tuple(self._events)

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for i, ev in enumerate(self._events):
            if ev["seq"] != i or ev["prev"] != prev:
                return False
            expect = object_hash({"prev": ev["prev"], "seq": ev["seq"], "kind": ev["kind"],
                                  "day": ev["day"], "body": ev["body"]})
            if ev["hash"] != expect:
                return False
            prev = ev["hash"]
        return True

    # -- guards ---------------------------------------------------------------
    def _guard_deadline(self) -> None:
        if self.now_day > self.job.deadline_day and self.state not in TERMINAL:
            raise EscrowError(
                f"deadline_day {self.job.deadline_day} passed (now {self.now_day}); "
                "run timeout() instead — a stale job must refund, never settle"
            )

    def tick(self, day: int) -> None:
        """Advance protocol time; refuses to go backwards (single-writer beats)."""
        if day < self.now_day:
            raise EscrowError("time moves forward only")
        self.now_day = day

    # -- transitions ----------------------------------------------------------
    def fire(self, event: str, **body) -> str:
        if self.state in TERMINAL:
            raise EscrowError(f"terminal state {self.state} accepts no events")
        key = (self.state, event)
        if key not in TRANSITIONS:
            raise EscrowError(f"illegal transition {self.state} --{event}--> (fail-closed)")
        if event != "timeout":
            self._guard_deadline()
        nxt = TRANSITIONS[key]

        if event == "fund":
            if self.job.escrow_usds_muc <= 0:
                raise EscrowError("cannot fund a job with an empty escrow")
            self.funded_by = body.get("from", self.funded_by)
        elif event == "claim":
            if body.get("worker") == self.funded_by:
                raise EscrowError("self-dealing: funder cannot claim its own job")
            self._append("claim", {"worker": body["worker"]})
            self.state = nxt
            return self._events[-1]["hash"]
        elif event == "deliver":
            self.claim = body["claim"]
        elif event == "verify_pass":
            if body.get("verifier") in ("", None):
                raise EscrowError("verify_pass requires an independent verifier")
            fee = bps_of(self.job.escrow_usds_muc, COORDINATION_FEE_BPS)
            self.fee_muc = fee
            self.worker_payout_muc = self.job.escrow_usds_muc - fee
        elif event in ("resolve_worker", "resolve_budget"):
            if not body.get("arbiter"):
                raise EscrowError("dispute resolution requires a named arbiter (witness band)")

        self._append(event, {k: v for k, v in body.items()})
        self.state = nxt
        return self._events[-1]["hash"]

    def timeout(self) -> str:
        """Deadline path: refund whatever is still escrowed, zero fees taken."""
        if self.state in TERMINAL:
            raise EscrowError(f"terminal state {self.state} accepts no events")
        if self.now_day <= self.job.deadline_day:
            raise EscrowError("deadline not reached; use cancel() if the budget withdraws")
        return self.fire("timeout", reason="deadline")
