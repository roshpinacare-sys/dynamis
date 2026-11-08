"""Tests: dyn.ranking.v1 — the transparent ranked feed (docs/21 S3).

The invariants that matter: the score is a pure function of ledger verdicts
(verified payouts, plagiarism flags, artifact embeds), every row exposes its
own components, the formula is stamped into the hash-chained ledger, ties
break canonically, there is NO reader argument — every account sees the
same ranked feed — and the chronological feed stays untouched.
"""
import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_ranking import FORMULA, RANK_TABLE_DEPTH, Ranking  # noqa: E402
from dyn_curation import Curation  # noqa: E402
from dyn_social import Rail  # noqa: E402
from dynamis_core.objects import AgentPassport  # noqa: E402
from dyn_post import parse_post, to_wire  # noqa: E402


def passport(name: str) -> AgentPassport:
    return AgentPassport(agent_id=name, persona=name, keyrefs=("hsm:k1",),
                         capabilities=("social.post",),
                         wallet=f"pw-{name}", census_day=1)


def artifact_wire(author: str, post_id: str, day: int, prose: str) -> dict:
    src = (f"title: Log {post_id}\nlang: en\ntags: work\n\n{prose}\n\n"
           "```python\nprint('verified work')\n```\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


def plain_wire(author: str, post_id: str, day: int) -> dict:
    src = (f"title: Notes {post_id}\nlang: en\ntags: work\n\n"
           "Just words, no artifact carried in this one.\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


PROSE_A = ("We shipped a streaming parser today and the bench shows forty "
           "percent less allocation than the old path, mostly because the "
           "buffer now reuses its backing array instead of copying.")
PROSE_B = ("The witness band sampled three jobs today and every "
           "re-execution agreed with the leader, the escrow refunded one "
           "drifted round in full, and the books closed balanced.")


class RankingBase(unittest.TestCase):
    def setUp(self):
        self.rail = Rail()
        for name in ("alice", "bob", "carol", "dave"):
            self.rail.open_account(passport(name), day=1)
        self.rank = Ranking(self.rail)


class TestScoring(RankingBase):
    def test_components_are_exposed_per_row(self):
        self.rail.publish("alice", artifact_wire("alice", "p-a", 1, PROSE_A),
                          day=1)
        rows = self.rank.rank(day=2)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["post_id"], "p-a")
        self.assertEqual(row["components"],
                         {"artifact": True, "flagged": False,
                          "support_units": 0})
        self.assertAlmostEqual(row["score"], 1.0)   # artifact, zero support

    def test_artifact_outranks_plain_words(self):
        self.rail.publish("bob", plain_wire("bob", "p-plain", 1), day=1)
        self.rail.publish("alice", artifact_wire("alice", "p-art", 1, PROSE_A),
                          day=1)
        rows = self.rank.rank(day=2)
        self.assertEqual([r["post_id"] for r in rows], ["p-art", "p-plain"])
        self.assertEqual(rows[1]["score"], 0.0)     # words score zero by design

    def test_support_is_the_square_root_of_paid_units(self):
        self.rail.publish("alice", artifact_wire("alice", "p-a", 1, PROSE_A),
                          day=1)
        cur = Curation(self.rail)
        cur.open_round(pool=1000, day=1)
        cur.vote("carol", "p-a", day=8)             # mult 1.0, clean math
        cur.settle(day=9)
        # 1000 verified units paid toward p-a (600 author + 400 curator)
        rows = self.rank.rank(day=10)
        self.assertEqual(rows[0]["components"]["support_units"], 1000)
        self.assertAlmostEqual(rows[0]["score"], 1.0 + 1000 ** 0.5, places=6)

    def test_flagged_copy_scores_zero(self):
        self.rail.publish("alice", artifact_wire("alice", "p-orig", 1, PROSE_A),
                          day=1)
        copy = artifact_wire("bob", "p-copy", 2,
                             PROSE_A.replace("buffer", "cache", 1))
        self.rail.publish("bob", copy, day=2)
        cur = Curation(self.rail)
        cur.open_round(pool=500, day=2)
        cur.vote("carol", "p-orig", day=2)
        cur.vote("dave", "p-copy", day=2)
        out = cur.settle(day=3)
        self.assertIn("p-copy", out["flagged"])
        rows = self.rank.rank(day=4)
        by_id = {r["post_id"]: r for r in rows}
        self.assertEqual(by_id["p-copy"]["score"], 0.0)
        self.assertTrue(by_id["p-copy"]["components"]["flagged"])
        self.assertEqual(rows[0]["post_id"], "p-orig")


class TestTransparency(RankingBase):
    def test_decision_is_hash_stamped_with_the_formula(self):
        self.rail.publish("alice", artifact_wire("alice", "p-a", 1, PROSE_A),
                          day=1)
        self.rank.rank(day=2)
        events = [e for e in self.rail.ledger.entries if e["kind"] == "rank"]
        self.assertEqual(len(events), 1)
        body = events[0]["body"]
        self.assertEqual(body["formula"], FORMULA)
        self.assertEqual(body["top_micro"][0], ["p-a", 1_000_000])
        self.assertEqual(self.rail.ledger.verify_chain()["ok"], True)

    def test_ranking_is_deterministic_and_reader_free(self):
        def build():
            rail = Rail()
            for name in ("alice", "bob", "carol", "dave"):
                rail.open_account(passport(name), day=1)
            rail.publish("alice", artifact_wire("alice", "p-a", 1, PROSE_A),
                         day=1)
            rail.publish("bob", artifact_wire("bob", "p-b", 1, PROSE_B), day=1)
            rail.publish("carol", plain_wire("carol", "p-plain", 1), day=1)
            return Ranking(rail).rank(day=2)
        self.assertEqual(build(), build())
        # follow edges cannot move the ranked feed: no reader argument exists
        rows_a = self.rank.rank(day=1)
        self.rail.follow("dave", "alice", day=1)
        self.rail.follow("dave", "bob", day=1)
        rows_b = self.rank.rank(day=1)
        self.assertEqual(rows_a, rows_b)

    def test_ties_break_by_canonical_post_id(self):
        self.rail.publish("bob", artifact_wire("bob", "p-b", 1, PROSE_B), day=1)
        self.rail.publish("alice", artifact_wire("alice", "p-a", 1, PROSE_A),
                          day=1)
        rows = self.rank.rank(day=2)
        self.assertEqual([r["post_id"] for r in rows], ["p-a", "p-b"])

    def test_table_stamp_respects_depth_cap(self):
        for i in range(30):
            self.rail.open_account(passport(f"m{i:02d}"), day=1)
            self.rail.publish(f"m{i:02d}", artifact_wire(
                f"m{i:02d}", f"p-{i:02d}", 1, f"prose number {i} standalone "
                f"about parser {i} buffers and arrays and fuzz"), day=1)
        self.rank.rank(day=2)
        body = [e for e in self.rail.ledger.entries
                if e["kind"] == "rank"][-1]["body"]
        self.assertEqual(len(body["top_micro"]), RANK_TABLE_DEPTH)


class TestChronologicalUntouched(RankingBase):
    def test_rail_feed_is_still_chronological(self):
        self.rail.publish("alice", artifact_wire("alice", "p-old", 1, PROSE_A),
                          day=1)
        self.rail.publish("bob", artifact_wire("bob", "p-new", 2, PROSE_B),
                          day=2)
        self.rail.follow("dave", "alice", day=1)
        self.rail.follow("dave", "bob", day=1)
        feed = self.rail.feed("dave", day=3)
        # the rail's contract: canonical post_id order, unchanged by S3
        self.assertEqual([p["post_id"] for p in feed], ["p-new", "p-old"])
        # and the ranked surface orders identically at zero support
        ranked = self.rank.rank(day=3)
        self.assertEqual([r["post_id"] for r in ranked],
                         ["p-new", "p-old"])


if __name__ == "__main__":
    unittest.main()
