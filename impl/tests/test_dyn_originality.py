"""Tests: dyn.originality.v1 — corpus originality at reward time (docs/21 S2).

The invariants that matter: similarity is measured on prose (front-matter
excluded), against every earlier post including the author's own; a copy
earns nothing, is flagged in the hash-chained ledger, and its author's
standing is cut; originals are untouched; the planted-corpus capture rate
is what the strategy doc demands (docs/21 §5: >90%).
"""
import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_curation import Curation  # noqa: E402
from dyn_originality import (Originality, PLAGIARISM_THRESHOLD,
                             _prose, shingles, similarity)  # noqa: E402
from dyn_social import Rail  # noqa: E402
from dynamis_core.objects import AgentPassport  # noqa: E402
from dyn_post import parse_post, to_wire  # noqa: E402


def passport(name: str) -> AgentPassport:
    return AgentPassport(agent_id=name, persona=name, keyrefs=("hsm:k1",),
                         capabilities=("social.post",),
                         wallet=f"pw-{name}", census_day=1)


ORIGINAL_PROSE = ("We shipped a streaming parser today and the bench shows "
                  "forty percent less allocation than the old path, mostly "
                  "because the buffer now reuses its backing array instead "
                  "of copying on every chunk boundary, and the fuzz suite "
                  "stays green across ten million random inputs.")


def wire_with_prose(author: str, post_id: str, day: int, prose: str,
                    title: str = "Build log") -> dict:
    src = (f"title: {title}\nlang: en\ntags: work\n\n{prose}\n\n"
           "```python\nprint('verified work')\n```\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


def near_copy(prose: str, swap: tuple[str, str]) -> str:
    return prose.replace(swap[0], swap[1], 1)


class OriginalityBase(unittest.TestCase):
    def setUp(self):
        self.rail = Rail()
        for name in ("alice", "bob", "carol", "dave"):
            self.rail.open_account(passport(name), day=1)
        self.cur = Curation(self.rail)


class TestSimilarity(unittest.TestCase):
    def test_identical_and_disjoint_prose(self):
        a = "the parser reuses its backing array on every chunk"
        b = "witnesses sample jobs and re-execute the check from scratch"
        self.assertEqual(similarity(a, a), 1.0)
        self.assertEqual(similarity(a, b), 0.0)

    def test_frontmatter_is_excluded_from_judgement(self):
        # same prose, different titles/tags: front-matter must not deflate
        # the score — the judged surface is the post's substance
        p1 = _prose("title: Alpha\nlang: en\ntags: work\n\nshared substance here\n")
        p2 = _prose("title: Beta\nlang: en\ntags: life\n\nshared substance here\n")
        self.assertEqual(similarity(p1, p2), 1.0)
        self.assertEqual(shingles("tiny"), {"tiny"})  # short-text fallback


class TestCorpusJudgement(OriginalityBase):
    def test_copied_post_is_caught(self):
        self.rail.publish("alice", wire_with_prose(
            "alice", "p-orig", 1, ORIGINAL_PROSE), day=1)
        self.rail.publish("bob", wire_with_prose(
            "bob", "p-copy", 2, near_copy(ORIGINAL_PROSE, ("buffer", "cache")),
            title="My log"), day=2)
        verdict = Originality(self.rail).judge("p-copy")
        self.assertTrue(verdict["plagiarized"])
        self.assertEqual(verdict["similar_to"], "p-orig")
        self.assertGreaterEqual(verdict["score"], PLAGIARISM_THRESHOLD)

    def test_original_post_passes(self):
        self.rail.publish("alice", wire_with_prose(
            "alice", "p-orig", 1, ORIGINAL_PROSE), day=1)
        other = ("The witness band sampled three jobs today and every "
                 "re-execution agreed with the leader, the escrow refunded "
                 "one drifted round in full, and the treasury report closed "
                 "balanced with the double-entry books for the first time.")
        self.rail.publish("bob", wire_with_prose(
            "bob", "p-mine", 2, other), day=2)
        verdict = Originality(self.rail).judge("p-mine")
        self.assertFalse(verdict["plagiarized"])

    def test_self_copy_is_caught_too(self):
        # double-earning your own substance is still plagiarism
        self.rail.publish("alice", wire_with_prose(
            "alice", "p-orig", 1, ORIGINAL_PROSE), day=1)
        self.rail.publish("alice", wire_with_prose(
            "alice", "p-self", 3, near_copy(ORIGINAL_PROSE, ("forty", "fifty"))),
            day=3)
        verdict = Originality(self.rail).judge("p-self")
        self.assertTrue(verdict["plagiarized"])
        self.assertEqual(verdict["similar_to"], "p-orig")


class TestSettleIntegration(OriginalityBase):
    def test_flagged_post_earns_nothing_and_standing_is_cut(self):
        self.rail.publish("alice", wire_with_prose(
            "alice", "p-orig", 1, ORIGINAL_PROSE), day=1)
        self.rail.publish("bob", wire_with_prose(
            "bob", "p-copy", 2, near_copy(ORIGINAL_PROSE, ("buffer", "cache"))),
            day=2)
        self.cur.open_round(pool=1000, day=2)
        self.cur.vote("carol", "p-orig", day=2)
        self.cur.vote("dave", "p-copy", day=2)
        out = self.cur.settle(day=3)
        # the copy is out of the split: the original takes the whole pool
        self.assertIn("p-copy", out["flagged"])
        self.assertEqual(out["payouts"], {"alice": 600, "carol": 400})
        self.assertEqual(out["unallocated"], 0)
        # the caught author's standing is cut to the floor
        self.assertEqual(self.cur.standing["bob"], 0.0)
        refusals = self.rail.ledger.refusals("REFUSED-PLAGIARY")
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["actor"], "bob")
        self.assertEqual(self.rail.ledger.verify_chain()["ok"], True)

    def test_planted_corpus_capture_rate(self):
        # five distinct originals; two planted copies by other authors —
        # the doc's success metric: >90% capture on a planted corpus
        proses = [
            "The treasury report closed balanced and the emission curve "
            "held its cap for the sixth week running without exception.",
            "Onboarding measured four minutes twelve seconds end to end "
            "from a cold framework install to a first published artifact.",
            "The escrow refunded a drifted round in full today and the "
            "buyer re-opened against the new study within the same hour.",
            "Curation clipped a whale to the cap and the mice split the "
            "remainder, exactly as the anti-capture mechanics intended.",
            "The ledger verified to depth nine thousand with every "
            "checkpoint root matching the merkle rollup of the day.",
        ]
        for i, prose in enumerate(proses):
            author = ["alice", "bob", "carol", "dave", "e03"][i]
            if author == "e03":
                self.rail.open_account(passport("e03"), day=1)
            self.rail.publish(author, wire_with_prose(
                author, f"p-orig-{i}", i + 1, prose), day=i + 1)
        self.rail.publish("bob", wire_with_prose(
            "bob", "p-copy-a", 6, near_copy(proses[0], ("sixth", "seventh"))),
            day=6)
        self.rail.publish("dave", wire_with_prose(
            "dave", "p-copy-b", 7, near_copy(proses[2], ("drifted", "stalled"))),
            day=7)
        orig = Originality(self.rail)
        caught = [pid for pid in ("p-copy-a", "p-copy-b")
                  if orig.judge(pid)["plagiarized"]]
        self.assertEqual(caught, ["p-copy-a", "p-copy-b"])  # 2/2 = 100%

    def test_settle_is_deterministic_with_flags(self):
        def build():
            rail = Rail()
            for name in ("alice", "bob", "carol", "dave"):
                rail.open_account(passport(name), day=1)
            rail.publish("alice", wire_with_prose(
                "alice", "p-orig", 1, ORIGINAL_PROSE), day=1)
            rail.publish("bob", wire_with_prose(
                "bob", "p-copy", 2,
                near_copy(ORIGINAL_PROSE, ("buffer", "cache"))), day=2)
            cur = Curation(rail)
            cur.open_round(pool=500, day=2)
            cur.vote("carol", "p-orig", day=2)
            cur.vote("dave", "p-copy", day=2)
            return cur.settle(day=3)
        self.assertEqual(build(), build())


if __name__ == "__main__":
    unittest.main()
