"""Anti-herd social scheduling (Laws 13–14) — the fleet's own PRNG, formalized.

`mulberry32(day|account)` seeds every schedule; the same seed reproduces the same
schedule post-hoc, which is what makes herd patterns detectable in others and honest
behavior provable in us. Caps per account-day (founding plan ch. 8): at most one
publish, two fleet votes, two replies; a minimum gap between actions; vote targets
steer toward the least-supported sibling post (anti-herd by construction).
"""
from __future__ import annotations

from typing import Iterator

DAILY_PUBLISH_CAP = 1
DAILY_VOTE_CAP = 2
DAILY_REPLY_CAP = 2
MIN_GAP_SLOTS = 3  # slots between any two actions of the same account


def mulberry32(seed: int) -> Iterator[int]:
    """The fleet's mulberry32, bit-exact to the reference implementation:
    var t = a += 0x6D2B79F5;
    t = imul(t ^ t>>>15, t | 1);
    t ^= t + imul(t ^ t>>>7, t | 61);
    return (t ^ t>>>14) >>> 0;"""
    a = seed & 0xFFFFFFFF
    while True:
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (a | 1)) & 0xFFFFFFFF
        t ^= (t + ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        yield (t ^ (t >> 14)) & 0xFFFFFFFF


def day_account_seed(day: int, account: str) -> int:
    """Law 14's seed: day|account — the '|' is the fleet's string-concat convention."""
    h = 2166136261
    for ch in f"{day}|{account}":
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def schedule_account(day: int, account: str, slots: int = 48,
                     active: bool = True) -> dict:
    """Deterministic schedule for one account on one day.

    slots = 30-minute slots (48/day). Actions are placed with gaps enforced; caps are
    hard. `active=False` is the rest-day draw — roughly one day in five rests, so the
    fleet does not breathe in unison (that would be a Sybil signature, Law 14).
    """
    rng = mulberry32(day_account_seed(day, account))
    if not active and (next(rng) % 5 != 0):
        return {"day": day, "account": account, "actions": [], "rest": True}

    actions: list[dict] = []
    used: list[int] = []
    for kind, cap in (("publish", DAILY_PUBLISH_CAP),
                      ("vote", DAILY_VOTE_CAP),
                      ("reply", DAILY_REPLY_CAP)):
        for _ in range(cap):
            for _attempt in range(16):
                slot = next(rng) % slots
                if all(abs(slot - u) >= MIN_GAP_SLOTS for u in used):
                    used.append(slot)
                    actions.append({"kind": kind, "slot": slot})
                    break
    actions.sort(key=lambda a: (a["slot"], a["kind"]))
    return {"day": day, "account": account, "actions": actions, "rest": not actions}


def least_supported(support_counts: dict[str, int]) -> str:
    """Anti-herd vote target: the least-supported sibling. Ties break deterministically
    by name so the choice is reproducible post-hoc."""
    if not support_counts:
        raise ValueError("no candidates")
    return min(support_counts, key=lambda k: (support_counts[k], k))
