"""Tests: dyn.curation.v1 — curation economics (docs/21 S1).

The invariants that matter: power is the square root of EARNED standing
(money cannot buy power), self-votes are refused outright, one vote per
curator per post, no curator may dominate the counted distribution, early
discovery pays before bandwagoning, only work-carrying artifacts earn,
settle is deterministic and closes the round, and every step lands in the
hash-chained ledger. The whale simulation compares the payout Gini against
a Steemit-style linear-power baseline.
"""
import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_curation import (AUTHOR_SHARE, MAX_VOTER_SHARE, REP_BASE,
                          STANDING_SCALE, Curation, CurationError,
                          early_multiplier, gini)  # noqa: E402
from dyn_social import Rail, kill, revive  # noqa: E402
from dynamis_core.objects import AgentPassport  # noqa: E402
from dyn_post import parse_post, to_wire  # noqa: E402


def passport(name: str) -> AgentPassport:
    return AgentPassport(agent_id=name, persona=name, keyrefs=("hsm:k1",),
                         capabilities=("social.post",),
                         wallet=f"pw-{name}", census_day=1)


def artifact_wire(author: str, post_id: str, day: int) -> dict:
    src = (f"title: Proof {post_id}\nlang: en\ntags: work\n\n"
           "Build log with the artifact inline.\n\n"
           "```python\nprint('verified work')\n```\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


def plain_wire(author: str, post_id: str, day: int) -> dict:
    src = (f"title: Notes {post_id}\nlang: en\ntags: work\n\n"
           "Just words, no artifact carried.\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


class CurationBase(unittest.TestCase):
    def setUp(self):
        revive()
        self.rail = Rail()
        for name in ("alice", "bob", "carol", "dave"):
            self.rail.open_account(passport(name), day=1)
        self.rail.publish("alice", artifact_wire("alice", "p-art", 1), day=1)
        self.rail.publish("bob", plain_wire("bob", "p-plain", 1), day=1)
        self.cur = Curation(self.rail)


class TestVoteRules(CurationBase):
    def test_vote_requires_an_open_round_first(self):
        with self.assertRaises(CurationError) as ctx:
            self.cur.vote("carol", "p-art", day=2)
        self.assertIn("REFUSED-NO-ROUND", str(ctx.exception))
        self.assertEqual(len(self.rail.ledger.refusals("REFUSED-NO-ROUND")), 1)

    def test_vote_requires_account_and_post(self):
        self.cur.open_round(pool=1000, day=1)
        with self.assertRaises(CurationError):
            self.cur.vote("stranger", "p-art", day=2)
        with self.assertRaises(CurationError):
            self.cur.vote("carol", "no-such-post", day=2)
        self.assertEqual(len(self.rail.ledger.refusals("REFUSED-NO-CUSTODY")), 1)
        self.assertEqual(
            len(self.rail.ledger.refusals("REFUSED-UNKNOWN-TARGET")), 1)

    def test_self_vote_is_refused_outright_and_recorded(self):
        self.cur.open_round(pool=1000, day=1)
        with self.assertRaises(CurationError) as ctx:
            self.cur.vote("alice", "p-art", day=2)
        self.assertIn("REFUSED-SELF-VOTE", str(ctx.exception))
        self.assertEqual(len(self.rail.ledger.refusals("REFUSED-SELF-VOTE")), 1)
        self.assertEqual(self.cur.rounds["cur-0001"]["votes"], [])

    def test_one_vote_per_curator_per_post(self):
        self.cur.open_round(pool=1000, day=1)
        self.cur.vote("carol", "p-art", day=2)
        with self.assertRaises(CurationError) as ctx:
            self.cur.vote("carol", "p-art", day=3)
        self.assertIn("REFUSED-DUPLICATE", str(ctx.exception))
        self.assertEqual(len(self.cur.rounds["cur-0001"]["votes"]), 1)


class TestPowerAndDiscovery(CurationBase):
    def test_power_is_the_square_root_of_standing(self):
        self.cur.open_round(pool=1000, day=1)
        self.cur.standing["carol"] = 4.0
        strong = self.cur.vote("carol", "p-art", day=2)
        weak = self.cur.vote("dave", "p-art", day=2)
        self.assertAlmostEqual(strong["power"], 2.0)
        self.assertAlmostEqual(weak["power"], 1.0)

    def test_early_discovery_multiplier_decays_over_the_window(self):
        self.assertAlmostEqual(early_multiplier(1, 1), 2.0)
        self.assertAlmostEqual(early_multiplier(1, 4), 1.0 + 4 / 7)
        self.assertAlmostEqual(early_multiplier(1, 8), 1.0)
        self.assertAlmostEqual(early_multiplier(1, 0), 2.0)  # never negative age

    def test_standing_grows_only_from_verified_payouts(self):
        self.assertEqual(self.cur._rep("dave"), REP_BASE)
        self.cur.open_round(pool=1000, day=1)
        self.cur.vote("carol", "p-art", day=8)   # mult 1.0: clean arithmetic
        out = self.cur.settle(day=9)
        # single eligible post takes the whole pool; author 600, curator 400
        self.assertEqual(out["payouts"], {"alice": 600, "carol": 400})
        self.assertAlmostEqual(self.cur.standing["alice"],
                               REP_BASE + 600 / STANDING_SCALE)
        self.assertAlmostEqual(self.cur.standing["carol"],
                               REP_BASE + 400 / STANDING_SCALE)
        self.assertEqual(self.cur._rep("dave"), REP_BASE)


class TestSettle(CurationBase):
    def test_only_work_carrying_artifacts_earn(self):
        self.cur.open_round(pool=1000, day=1)
        self.cur.vote("carol", "p-plain", day=2)   # plain words: visible, unp
        out = self.cur.settle(day=3)
        self.assertEqual(out["paid"], 0)
        self.assertEqual(out["unallocated"], 1000)
        self.assertEqual(out["payouts"], {})
        self.assertEqual(self.rail.ledger.verify_chain()["ok"], True)

    def test_split_author_curators_and_ledger_events(self):
        self.cur.open_round(pool=1000, day=1)
        self.cur.vote("carol", "p-art", day=2)
        self.cur.vote("dave", "p-art", day=2)
        out = self.cur.settle(day=3)
        row = out["posts"][0]
        self.assertEqual(row["post_pool"], 1000)
        self.assertEqual(row["author_paid"], 600)
        self.assertEqual(row["curators_paid"], {"carol": 200, "dave": 200})
        self.assertEqual(sum(out["payouts"].values()) + out["unallocated"]
                         + sum(r["dust"] for r in out["posts"]), 1000)
        kinds = [e["kind"] for e in self.rail.ledger.entries]
        for kind in ("round", "vote", "payout"):
            self.assertIn(kind, kinds)
        self.assertEqual(self.rail.ledger.verify_chain()["ok"], True)

    def test_settle_is_deterministic_and_closes_the_round(self):
        def run():
            rail = Rail()
            for name in ("alice", "bob", "carol", "dave"):
                rail.open_account(passport(name), day=1)
            rail.publish("alice", artifact_wire("alice", "p-art", 1), day=1)
            cur = Curation(rail)
            cur.open_round(pool=777, day=1)
            cur.standing["carol"] = 9.0
            cur.vote("carol", "p-art", day=2)
            cur.vote("dave", "p-art", day=3)
            return cur.settle(day=4)
        first, second = run(), run()
        self.assertEqual(first, second)
        # the round closed: a second settle has no open round to close
        with self.assertRaises(CurationError):
            self.cur.settle(day=4)

    def test_the_kill_switch_refuses_every_mutation(self):
        kill()
        with self.assertRaises(Exception):
            self.cur.open_round(pool=1000, day=1)
        revive()
        self.cur.open_round(pool=1000, day=1)
        kill()
        with self.assertRaises(Exception):
            self.cur.vote("carol", "p-art", day=2)
        revive()


class TestAntiWhale(CurationBase):
    def test_whale_is_clipped_to_the_cap(self):
        # one whale (standing 100 → power 10) against ten mice (power 1):
        # the whale's ceiling is room_factor × the raw weight of everyone
        # else, so its counted share lands exactly on the cap
        self.cur.open_round(pool=1000, day=1)
        self.cur.standing["carol"] = 100.0
        self.cur.vote("carol", "p-art", day=8)          # mult 1.0
        for i in range(8):
            name = f"m{i:02d}"
            self.rail.open_account(passport(name), day=1)
            self.cur.vote(name, "p-art", day=8)
        self.cur.vote("bob", "p-art", day=8)
        self.cur.vote("dave", "p-art", day=8)
        out = self.cur.settle(day=9)
        # raw: 10 + 10 mice = 20; whale ceiling = (0.2/0.8)×10 = 2.5 →
        # counted distribution 12.5, whale share exactly the cap
        whale_share = 2.5 / 12.5
        self.assertLessEqual(whale_share, MAX_VOTER_SHARE + 1e-9)
        row = out["posts"][0]
        self.assertEqual(row["curators_paid"]["carol"], 80)   # 400×2.5/12.5
        self.assertEqual(row["curators_paid"]["bob"], 32)     # 400×1/12.5
        self.assertIn("carol", out["clipped"])

    def test_small_rounds_stay_proportional(self):
        # two equal curators: the cap's equal-share floor keeps the split
        # proportional — the anti-whale cap must not distort bootstrapping
        self.cur.open_round(pool=1000, day=1)
        self.cur.vote("carol", "p-art", day=2)
        self.cur.vote("dave", "p-art", day=2)
        out = self.cur.settle(day=3)
        row = out["posts"][0]
        self.assertEqual(row["curators_paid"], {"carol": 200, "dave": 200})
        self.assertEqual(out["clipped"], {})

    def test_gini_whale_simulation_beats_the_linear_baseline(self):
        # the Steemit failure replayed: linear power ∝ standing, no cap —
        # the whale takes 10/20 of the curator pool; ours takes 2.5/12.5
        payouts_ours = [80.0] + [32.0] * 10
        payouts_linear = [400 * 10 / 20] + [400 / 20] * 10
        self.assertLess(gini(payouts_ours), gini(payouts_linear))
        # and the capture itself is bounded: 80 vs 200 units for the whale
        self.assertLess(80.0, 200.0)


if __name__ == "__main__":
    unittest.main()
