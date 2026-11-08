#!/usr/bin/env python3
"""dyn.curation.v1 — curation economics: votes that discover, not buy (docs/21 S1).

Steemit's reward pool was captured because voting power was linear in stake,
self-voting paid, and payouts were unconditional. This layer answers each
failure mechanically (docs/21 §2–3), on the social rail's own terms:

  - power = sqrt(standing): standing is EARNED — every unit the network pays
    a verified recipient raises that account's standing at a fixed rate, and
    nothing in the rail sells standing, so money cannot buy power (F1, F2)
  - self-votes are refused outright, and the refusal lands in the ledger (F4)
  - one vote per curator per post; anti-whale cap: no curator may count for
    more than MAX_VOTER_SHARE of the counted distribution — with an equal-
    share floor so bootstrapping rounds stay proportional (F1)
  - early discovery: votes near publish day carry a multiplier that decays
    linearly to nothing across the window — curation rewards finding, not
    bandwagoning (F2)
  - payout gate: only work-carrying artifacts (embeds >= 1) earn; a plain
    post is visible but cannot pay (F3, F6 — Law 13 at the social layer)
  - author/curator split per post; every payout is a hash-chained ledger
    event; settle is deterministic and closes the round (F7: transparent)
"""
from __future__ import annotations

import math

from dyn_social import Rail, SocialError, _check_kill

CUR = "dyn.curation.v1"

AUTHOR_SHARE = 0.6        # the artifact's author; curators split the rest
MAX_VOTER_SHARE = 0.2     # anti-whale cap on one curator's counted share
EARLY_WINDOW_DAYS = 7     # the discovery bonus decays to zero over this window
EARLY_BONUS = 1.0         # ×(1+bonus) at publish day, ×1.0 at window's end
STANDING_SCALE = 100.0    # units of verified payout per +1 standing
REP_BASE = 1.0            # a fresh account's standing


class CurationError(SocialError):
    pass


def early_multiplier(post_day: int, vote_day: int,
                     window: int = EARLY_WINDOW_DAYS) -> float:
    """1+EARLY_BONUS on publish day, decaying linearly to 1.0 at window's end."""
    age = max(0, vote_day - post_day)
    return 1.0 + EARLY_BONUS * max(0.0, 1.0 - age / window)


def gini(values: list[float]) -> float:
    """Gini coefficient of a payout distribution (0 = equal, 1 = captured)."""
    xs = sorted(values)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total == 0:
        return 0.0
    weighted = sum((i + 1) * x for i, x in enumerate(xs))
    return (2.0 * weighted - (n + 1) * total) / (n * total)


class Curation:
    """One curation ledger over a social rail: rounds, votes, settle."""

    def __init__(self, rail: Rail) -> None:
        self.rail = rail
        self.standing: dict[str, float] = {}
        self.rounds: dict[str, dict] = {}
        self.closed: set[str] = set()
        self._seq = 0

    def _rep(self, agent: str) -> float:
        return self.standing.get(agent, REP_BASE)

    def _refuse(self, actor: str, day: int, reason: str, what: str) -> None:
        self.rail.ledger.append(day=day, kind="refused", actor=actor,
                                body={"reason": reason, "what": what})
        raise CurationError(f"{reason}: {what}")

    # ---------- rounds ----------
    def _open_round_id(self) -> str | None:
        for rid in sorted(self.rounds):
            if rid not in self.closed:
                return rid
        return None

    def open_round(self, *, pool: int, day: int) -> str:
        _check_kill()
        if pool <= 0:
            self._refuse("curation", day, "REFUSED-POOL", "pool must be positive")
        if self._open_round_id() is not None:
            self._refuse("curation", day, "REFUSED-DUPLICATE", "a round is open")
        self._seq += 1
        rid = f"cur-{self._seq:04d}"
        self.rounds[rid] = {"pool": pool, "opened_day": day, "votes": []}
        self.rail.ledger.append(day=day, kind="round", actor=rid,
                                body={"pool": pool})
        return rid

    # ---------- votes ----------
    def vote(self, curator: str, post_id: str, *, day: int) -> dict:
        _check_kill()
        rid = self._open_round_id()
        if rid is None:
            self._refuse(curator, day, "REFUSED-NO-ROUND", "no open round")
        if curator not in self.rail.accounts:
            self._refuse(curator, day, "REFUSED-NO-CUSTODY",
                         "curator has no account")
        if post_id not in self.rail.posts:
            self._refuse(curator, day, "REFUSED-UNKNOWN-TARGET", "no such post")
        if curator == self.rail.author_of[post_id]:
            self._refuse(curator, day, "REFUSED-SELF-VOTE",
                         "a curator cannot vote on their own artifact")
        if any(v["curator"] == curator and v["post_id"] == post_id
               for v in self.rounds[rid]["votes"]):
            self._refuse(curator, day, "REFUSED-DUPLICATE",
                         "already voted on this post")
        power = math.sqrt(self._rep(curator))
        row = {"curator": curator, "post_id": post_id, "day": day,
               "power": power,
               "mult": early_multiplier(self.rail.posts[post_id]["day"], day)}
        self.rounds[rid]["votes"].append(row)
        self.rail.ledger.append(day=day, kind="vote", actor=curator,
                                body={"round": rid, "post_id": post_id,
                                      "power_micro": int(round(power * 10**6)),
                                      "mult_micro": int(round(row["mult"] * 10**6))})
        return dict(row)

    # ---------- settle: deterministic, closes the round ----------
    def settle(self, *, day: int) -> dict:
        _check_kill()
        rid = self._open_round_id()
        if rid is None:
            self._refuse("curation", day, "REFUSED-NO-ROUND", "no open round")
        rnd = self.rounds[rid]
        votes = sorted(rnd["votes"],
                       key=lambda v: (v["post_id"], v["curator"]))

        # anti-whale: a curator may never count for more than MAX_VOTER_SHARE
        # of the counted distribution — or more than an equal share when the
        # round has fewer voters than the cap admits (bootstrapping rounds
        # stay proportional; capture needs a crowd, and a crowd is capped).
        # Each ceiling is computed against the RAW weight of everyone else,
        # so the cap is symmetric and order-independent.
        raw: dict[str, float] = {}
        for v in votes:
            raw[v["curator"]] = (raw.get(v["curator"], 0.0)
                                 + v["power"] * v["mult"])
        raw_total = sum(raw.values())
        cap = max(MAX_VOTER_SHARE, 1.0 / len(raw)) if raw else MAX_VOTER_SHARE
        clip: dict[str, float] = {}
        if cap < 1.0:
            room_factor = cap / (1.0 - cap)
            for curator, w in raw.items():
                ceiling = room_factor * (raw_total - w)
                if w > ceiling:
                    clip[curator] = ceiling / w

        # payout gate: only work-carrying artifacts earn (Law 13)
        by_post: dict[str, float] = {}
        for v in votes:
            w = v["power"] * v["mult"] * clip.get(v["curator"], 1.0)
            if len(self.rail.posts[v["post_id"]].get("embeds", [])) >= 1:
                by_post[v["post_id"]] = by_post.get(v["post_id"], 0.0) + w

        pool = rnd["pool"]
        eligible_total = sum(by_post.values())
        payouts: dict[str, int] = {}
        post_rows: list[dict] = []
        allocated = 0
        for pid in sorted(by_post):
            post_pool = math.floor(pool * by_post[pid] / eligible_total)
            allocated += post_pool
            author = self.rail.author_of[pid]
            author_paid = math.floor(post_pool * AUTHOR_SHARE)
            payouts[author] = payouts.get(author, 0) + author_paid
            curator_pool = post_pool - author_paid
            post_votes = sorted((v for v in votes if v["post_id"] == pid),
                                key=lambda v: v["curator"])
            weights = {v["curator"]:
                       v["power"] * v["mult"] * clip.get(v["curator"], 1.0)
                       for v in post_votes}
            w_sum = sum(weights.values())
            curators_paid: dict[str, int] = {}
            cur_allocated = 0
            for curator in sorted(weights):
                pay = (math.floor(curator_pool * weights[curator] / w_sum)
                       if w_sum else 0)
                cur_allocated += pay
                curators_paid[curator] = pay
                payouts[curator] = payouts.get(curator, 0) + pay
            post_rows.append({
                "post_id": pid, "author": author, "post_pool": post_pool,
                "author_paid": author_paid, "curators_paid": curators_paid,
                "dust": post_pool - author_paid - cur_allocated})
            self.rail.ledger.append(day=day, kind="payout", actor=author,
                                    body={"round": rid, "post_id": pid,
                                          "author_units": author_paid,
                                          "curators": curators_paid,
                                          "dust": post_rows[-1]["dust"]})
        unallocated = pool - allocated
        for actor, pay in sorted(payouts.items()):
            self.standing[actor] = self._rep(actor) + pay / STANDING_SCALE
        self.closed.add(rid)
        self.rail.ledger.append(day=day, kind="round", actor=rid,
                                body={"settled_day": day, "paid": allocated,
                                      "unallocated": unallocated,
                                      "clipped": sorted(clip)})
        return {"round": rid, "pool": pool, "paid": allocated,
                "unallocated": unallocated, "clipped": clip,
                "posts": post_rows, "payouts": payouts,
                "curation_gini": gini(list(payouts.values()))}
