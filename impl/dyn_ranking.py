#!/usr/bin/env python3
"""dyn.ranking.v1 — the transparent ranked feed (docs/21 S3).

Steemit's trending page was a closed algorithm on top of a captured pool:
ranking rewarded what the whales had already voted. This layer ranks by the
verdicts the ledger already holds, and nothing else:

  - support(post)  = every verified unit the network paid toward the post
                     (author + curators, summed from `payout` events)
  - flagged(post)  = the post carries a REFUSED-PLAGIARY verdict (S2)
  - artifact(post) = the post carries its work (embeds >= 1)

score = artifact and not flagged ? 1 + sqrt(support) : 0

The formula is public, the inputs are ledger events, every row exposes its
own components, and each day's decision is hash-stamped into the ledger
(`rank` event, top table in integer micro-units). There is no reader
argument: every account sees the same ranked feed — no filter bubble to
tune, no engagement signal to farm, no closed algorithm to game. Plain
words score zero by design: the ranked surface is the artifact surface;
the chronological feed (Rail.feed) remains the home of everything else.
"""
from __future__ import annotations

import math

from dyn_social import Rail, _check_kill

RANKING = "dyn.ranking.v1"

RANK_TABLE_DEPTH = 20      # how many rows the daily ledger stamp carries
FORMULA = "artifact-only * (1 + sqrt(support)); flags score zero"


class Ranking:
    """Ranks posts by ledger verdicts; stamps each day's decision."""

    def __init__(self, rail: Rail) -> None:
        self.rail = rail

    def _verdicts(self) -> tuple[dict[str, int], set[str]]:
        """support and flags, read ONLY from the rail's ledger events."""
        support: dict[str, int] = {}
        flagged: set[str] = set()
        for e in self.rail.ledger.entries:
            if e["kind"] == "payout":
                body = e["body"]
                paid = body["author_units"] + sum(body["curators"].values())
                support[body["post_id"]] = support.get(body["post_id"], 0) + paid
            elif e["kind"] == "refused" \
                    and e["body"].get("reason") == "REFUSED-PLAGIARY":
                flagged.add(e["body"]["post_id"])
        return support, flagged

    def rank(self, *, day: int) -> list[dict]:
        """The day's ranked feed: every post with its full score components,
        best first, ties broken by canonical post_id. No reader argument —
        the ranked feed is the same for everyone."""
        _check_kill()
        support, flagged = self._verdicts()
        rows: list[dict] = []
        for pid in sorted(self.rail.posts):
            is_artifact = len(self.rail.posts[pid].get("embeds", [])) >= 1
            paid = support.get(pid, 0)
            score = (1.0 + math.sqrt(paid)) if is_artifact and pid not in flagged \
                else 0.0
            rows.append({"post_id": pid,
                         "author": self.rail.author_of[pid],
                         "score": score,
                         "components": {"artifact": is_artifact,
                                        "flagged": pid in flagged,
                                        "support_units": paid}})
        rows.sort(key=lambda r: (-r["score"], r["post_id"]))
        self.rail.ledger.append(
            day=day, kind="rank", actor="ranking",
            body={"formula": FORMULA,
                  "top_micro": [[r["post_id"], int(round(r["score"] * 10**6))]
                                for r in rows[:RANK_TABLE_DEPTH]]})
        return rows
