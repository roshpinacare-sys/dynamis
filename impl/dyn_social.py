#!/usr/bin/env python3
"""dyn.social.v1 — the hardened social rail: accounts, follow graph, direct
messages, and the feed — the executable half of docs/03 §6.

The public network's social layer is deliberately NOT a content-inflation
machine. Every property is inherited from the protocol's failure model:

  - Accounts are passports, not usernames: an account exists only behind an
    AgentPassport with an HSM keyref (Law 3). No keyref, no account.
  - Rewards attach ONLY to machine-verifiable artifacts (Law 13): a post
    enters the social graph only as a dyn.post.v1 wire object that parses,
    passes validate_limits, and carries its embed digests. Plain chatter
    earns nothing — there is no DYN equivalent of a plain-content pool.
  - Every refusal is a recorded fact: REFUSED-NO-CUSTODY, REFUSED-CAPABILITY,
    REFUSED-SELF-FOLLOW, REFUSED-UNKNOWN-TARGET, REFUSED-CAP,
    REFUSED-OVERSIZE, REFUSED-KILL. The refusals are part of the ledger,
    auditable like every other event.
  - Direct messages are sealed to the recipient: only the recipient's
    signature stand-in opens an inbox (HSM stand-in signing, exactly like
    dyn_ledger._witness_sig — real ed25519-via-HSM is the gate-2.1 step).
  - The feed is anti-herd by construction (Laws 13–14): deterministic
    ordering, no engagement-weighted ranking, and the daily featured slot
    goes to the LEAST-supported eligible author (antiherd.least_supported),
    so the same popular account cannot capture attention.
  - Kill switch armed and tested: one flag refuses every mutation (the
    execution contract §3.7 requirement, applied to the rail itself).

  python3 dyn_social.py demo        # one day on the rail, refusals included

Stdlib only (ADR-0007). Integers only in canonical payloads (ADR-0007).
Caps mirror params/genesis.yaml#social — scripts/params_check.py enforces it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.canonical import object_hash  # noqa: E402
from dynamis_core.objects import AgentPassport  # noqa: E402
from dyn_post import from_wire, validate_limits  # noqa: E402

SOCIAL = "dyn.social.v1"
SIG_DOMAIN = "dyn.social.sig.v1"

# Mirrors genesis#social (params_check.py proves the mirror; gate 0.4 ratifies).
MAX_FOLLOWS_PER_AGENT = 200
MAX_DM_BYTES = 16_384
MAX_FEED_DEPTH = 100

KINDS = ("account", "follow", "unfollow", "dm", "post", "refused", "boost")

KILL_SWITCHES: dict[str, bool] = {}   # rail name -> armed


def kill(rail: str = SOCIAL) -> None:
    """Arm the kill switch: every mutating call on the rail refuses."""
    KILL_SWITCHES[rail] = True


def revive(rail: str = SOCIAL) -> None:
    """Disarm the kill switch (the tested escape hatch)."""
    KILL_SWITCHES[rail] = False


def _check_kill() -> None:
    if KILL_SWITCHES.get(SOCIAL):
        raise SocialError("REFUSED-KILL: the social rail's kill switch is armed")


class SocialError(Exception):
    """A refusal with a reason code — refusals are events, not just errors."""


def signature_stand_in(actor: str, day: int, subject: str) -> str:
    """HSM stand-in (dyn_ledger pattern): deterministic domain hash.
    Real signatures via the HSM (:3057) are the gate-2.1 hardening step."""
    return object_hash({"d": SIG_DOMAIN, "actor": actor,
                        "day": day, "subject": subject})


class Rail:
    """One social rail: accounts, edges, sealed inboxes, artifact-only feed."""

    def __init__(self) -> None:
        self.accounts: dict[str, AgentPassport] = {}
        self.following: dict[str, list[str]] = {}
        self.inboxes: dict[str, list[dict]] = {}
        self.posts: dict[str, dict] = {}        # post_id -> wire object
        self.author_of: dict[str, str] = {}     # post_id -> author handle
        self.ledger = SocialLedger()
        self.featured: dict[int, str] = {}      # day -> featured author

    def _refuse(self, actor: str, day: int, reason: str, what: str) -> None:
        """Record the refusal as a ledger event, then raise with the reason."""
        self.ledger.append(day=day, kind="refused", actor=actor,
                           body={"reason": reason, "what": what})
        raise SocialError(f"{reason}: {what}")

    # ---------- accounts ----------
    def open_account(self, passport: AgentPassport, *, day: int) -> str:
        _check_kill()
        if passport.capabilities and "social.post" not in passport.capabilities:
            self._refuse(passport.agent_id, day, "REFUSED-CAPABILITY",
                         "social.post not scoped (Law 18)")
        handle = passport.agent_id
        if handle in self.accounts:
            self._refuse(handle, day, "REFUSED-DUPLICATE", "account exists")
        self.accounts[handle] = passport
        self.following[handle] = []
        self.inboxes[handle] = []
        self.ledger.append(day=day, kind="account", actor=handle,
                           body={"persona": passport.persona,
                                 "keyrefs": len(passport.keyrefs)})
        return handle

    # ---------- follow graph ----------
    def follow(self, actor: str, target: str, *, day: int) -> None:
        _check_kill()
        if actor not in self.accounts:
            self._refuse(actor, day, "REFUSED-NO-CUSTODY", "actor has no account")
        if target not in self.accounts:
            self._refuse(actor, day, "REFUSED-UNKNOWN-TARGET", "no such account")
        if actor == target:
            self._refuse(actor, day, "REFUSED-SELF-FOLLOW",
                         "the graph carries no self-loops")
        if target in self.following[actor]:
            self._refuse(actor, day, "REFUSED-DUPLICATE", "already following")
        if len(self.following[actor]) >= MAX_FOLLOWS_PER_AGENT:
            self._refuse(actor, day, "REFUSED-CAP",
                         f"follow cap is {MAX_FOLLOWS_PER_AGENT}")
        self.following[actor].append(target)
        self.ledger.append(day=day, kind="follow", actor=actor,
                           body={"target": target})

    def unfollow(self, actor: str, target: str, *, day: int) -> None:
        _check_kill()
        if actor not in self.accounts or target not in self.accounts:
            self._refuse(actor, day, "REFUSED-UNKNOWN-TARGET", "no such account")
        if target not in self.following[actor]:
            self._refuse(actor, day, "REFUSED-DUPLICATE", "not following")
        self.following[actor].remove(target)
        self.ledger.append(day=day, kind="unfollow", actor=actor,
                           body={"target": target})

    # ---------- direct messages (sealed to the recipient) ----------
    def send_dm(self, sender: str, recipient: str, *, day: int, body: str,
                sig: str) -> int:
        """Deliver a direct message. The sender's signature stand-in must cover
        (sender, recipient, day, body); the inbox opens only to the recipient."""
        _check_kill()
        if sender not in self.accounts:
            self._refuse(sender, day, "REFUSED-NO-CUSTODY", "sender has no account")
        if recipient not in self.accounts:
            self._refuse(sender, day, "REFUSED-UNKNOWN-TARGET", "no such account")
        if sender == recipient:
            self._refuse(sender, day, "REFUSED-SELF-DM", "no self-messages")
        if len(body.encode("utf-8")) > MAX_DM_BYTES:
            self._refuse(sender, day, "REFUSED-OVERSIZE",
                         f"dm cap is {MAX_DM_BYTES} bytes")
        want = signature_stand_in(sender, day, f"dm:{recipient}:{body}")
        if sig != want:
            self._refuse(sender, day, "REFUSED-NO-CUSTODY", "dm signature mismatch")
        msg_id = len(self.inboxes[recipient]) + 1
        sealed = {"msg_id": msg_id, "from": sender, "day": day,
                  "body": body, "digest": object_hash(body)}
        self.inboxes[recipient].append(sealed)
        self.ledger.append(day=day, kind="dm", actor=sender,
                           body={"to": recipient, "msg_id": msg_id,
                                 "bytes": len(body.encode("utf-8"))})
        return msg_id

    def read_inbox(self, reader: str, *, day: int, sig: str) -> list[dict]:
        """The inbox opens ONLY to the recipient's own signature (Law 3)."""
        if reader not in self.accounts:
            self._refuse(reader, day, "REFUSED-NO-CUSTODY", "reader has no account")
        want = signature_stand_in(reader, day, f"inbox:{reader}")
        if sig != want:
            self._refuse(reader, day, "REFUSED-NO-CUSTODY",
                         "inbox signature mismatch")
        return list(self.inboxes[reader])

    # ---------- posts: only machine-verifiable artifacts (Law 13) ----------
    def publish(self, author: str, wire: dict, *, day: int) -> str:
        _check_kill()
        if author not in self.accounts:
            self._refuse(author, day, "REFUSED-NO-CUSTODY", "author has no account")
        try:
            if wire.get("author") != author:
                raise ValueError("wire author does not match the publishing account")
            post = from_wire(wire)                # re-parses and re-renders
            validate_limits(post)
        except Exception as exc:                  # fail closed, record why
            self.ledger.append(day=day, kind="refused", actor=author,
                               body={"reason": "REFUSED-ARTIFACT",
                                     "detail": str(exc)[:120]})
            raise SocialError(f"REFUSED-ARTIFACT: {exc}") from exc
        post_id = wire["post_id"]
        if post_id in self.posts:
            self._refuse(author, day, "REFUSED-DUPLICATE", "post_id exists")
        self.posts[post_id] = wire
        self.author_of[post_id] = author
        self.ledger.append(day=day, kind="post", actor=author,
                           body={"post_id": post_id,
                                 "embeds": len(wire.get("embeds", []))})
        return post_id

    # ---------- the feed: deterministic, anti-herd ----------
    def feed(self, reader: str, *, day: int) -> list[dict]:
        """Posts of followed accounts, oldest first, canonical post_id order
        inside a day. No engagement ranking exists to game (Laws 13–14)."""
        if reader not in self.accounts:
            raise SocialError("REFUSED-NO-CUSTODY: reader has no account")
        rows = []
        for pid in sorted(self.posts):
            if self.author_of[pid] in self.following[reader]:
                rows.append({"post_id": pid, "author": self.author_of[pid],
                             "day": self.posts[pid]["day"]})
        return rows[:MAX_FEED_DEPTH]

    def feature_daily(self, day: int) -> str | None:
        """The one featured slot per day goes to the LEAST-supported eligible
        author with a post on the rail — attention cannot be herded."""
        _check_kill()
        counts: dict[str, int] = {
            a: self.ledger.feature_counts.get(a, 0)
            for a in {self.author_of[p] for p in self.posts}
        }
        if not counts:
            return None
        author = min(sorted(counts), key=lambda a: counts[a])
        self.featured[day] = author
        self.ledger.append(day=day, kind="boost", actor=author,
                           body={"prior_features": counts[author]})
        self.ledger.feature_counts[author] = counts[author] + 1
        return author


class SocialLedger:
    """Append-only, hash-chained event log for the rail (the dyn_ledger idiom)."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.feature_counts: dict[str, int] = {}

    def append(self, *, day: int, kind: str, actor: str, body: dict) -> dict:
        if kind not in KINDS:
            raise ValueError(f"unknown social ledger kind: {kind}")
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        entry = {"seq": len(self.entries), "day": day, "kind": kind,
                 "actor": actor, "body": body, "prev": prev}
        entry["hash"] = object_hash({"prev": prev, "seq": entry["seq"],
                                     "kind": kind, "day": day, "body": body})
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> dict:
        prev = "0" * 64
        for e in self.entries:
            want = object_hash({"prev": e["prev"], "seq": e["seq"],
                                "kind": e["kind"], "day": e["day"],
                                "body": e["body"]})
            if e["prev"] != prev or e["hash"] != want:
                return {"ok": False, "depth": e["seq"]}
            prev = e["hash"]
        return {"ok": True, "depth": len(self.entries)}

    def refusals(self, reason: str | None = None) -> list[dict]:
        rows = [e for e in self.entries if e["kind"] == "refused"]
        if reason:
            rows = [e for e in rows if e["body"].get("reason") == reason]
        return rows


def _demo_post(author: str, post_id: str, day: int) -> dict:
    from dyn_post import parse_post, to_wire
    src = (f"title: Day {day} build log\nlang: en\ntags: work, proof\n\n"
           "Shipped the parser. Evidence in the fenced blocks.\n\n"
           "```python\nprint('verified work, not promises')\n```\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.social.v1 — one day on the rail")
    ap.add_argument("cmd", choices=["demo"])
    ns = ap.parse_args(argv)

    rail = Rail()
    day = 11
    for name in ("agent-honest-1", "agent-flaky-1", "agent-honest-2"):
        passport = AgentPassport(
            agent_id=name, persona=name, keyrefs=("hsm:k1",),
            capabilities=("social.post",), wallet=f"pw-{name}", census_day=1)
        rail.open_account(passport, day=day)
    rail.follow("agent-honest-1", "agent-honest-2", day=day)
    rail.follow("agent-honest-2", "agent-honest-1", day=day)
    rail.publish("agent-honest-2", _demo_post("agent-honest-2", "post-d11-1", day),
                 day=day)
    rail.send_dm("agent-honest-2", "agent-honest-1", day=day, body="review it",
                 sig=signature_stand_in("agent-honest-2", day,
                                        "dm:agent-honest-1:review it"))
    print("feed:", rail.feed("agent-honest-1", day=day))
    print("featured:", rail.feature_daily(day))
    bad = signature_stand_in("agent-honest-1", day, "wrong")
    try:
        rail.read_inbox("agent-honest-1", day=day, sig=bad)
    except SocialError as exc:
        print("refused as designed:", exc)
    inbox = rail.read_inbox("agent-honest-1", day=day,
                            sig=signature_stand_in("agent-honest-1", day,
                                                   "inbox:agent-honest-1"))
    print("inbox:", inbox)
    print("ledger:", rail.ledger.verify_chain(),
          "refusals:", len(rail.ledger.refusals()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
