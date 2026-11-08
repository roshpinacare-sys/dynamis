#!/usr/bin/env python3
"""dyn.originality.v1 — corpus originality judging at reward time (docs/21 S2).

The last unverified reward surface was text itself: Steemit's proof-of-brain
paid plagiarism farms as readily as originals. Here a post's prose is judged
against the rail's own corpus — every earlier post, any author, including
the poster's own earlier work — by word-shingle Jaccard similarity. A post
whose substance is a copy is flagged at settle time: it earns nothing, the
flag is a hash-chained ledger event, and the caught author's standing is
cut. Originality is judged against what the network already holds, at the
moment rewards are computed — not by an after-the-fact complaint.

Known limit (documented, deterministic): posts share only a day
granularity, so a same-day copy is caught when its post_id sorts after the
original's; cross-day copying — the farm pattern — is always caught.
"""
from __future__ import annotations

from dyn_social import Rail

ORIGINALITY = "dyn.originality.v1"

SHINGLE_SIZE = 4            # word 4-grams
PLAGIARISM_THRESHOLD = 0.3  # Jaccard over shingle sets
STANDING_PENALTY = 1.0      # standing cut from a caught plagiarist


def _prose(body: str) -> str:
    """The body minus its front-matter (everything before the first blank
    line) — titles and tags must not inflate or deflate similarity."""
    parts = body.split("\n\n", 1)
    return parts[1] if len(parts) == 2 else body


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    words = text.lower().split()
    if len(words) < size:
        return set(words)
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def similarity(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class Originality:
    """Judges posts against the rail's own corpus, at reward time."""

    def __init__(self, rail: Rail) -> None:
        self.rail = rail

    def _prose_of(self, post_id: str) -> str:
        return _prose(self.rail.posts[post_id].get("body", ""))

    def judge(self, post_id: str) -> dict:
        """Best-match verdict for one post against all earlier posts."""
        text = self._prose_of(post_id)
        best_id, best_score = None, 0.0
        for other in sorted(self.rail.posts):
            if other == post_id:
                continue
            if self.rail.posts[other]["day"] > self.rail.posts[post_id]["day"]:
                continue
            score = similarity(text, self._prose_of(other))
            if score > best_score:
                best_id, best_score = other, score
        return {"post_id": post_id, "similar_to": best_id,
                "score": round(best_score, 4),
                "plagiarized": best_score >= PLAGIARISM_THRESHOLD}
