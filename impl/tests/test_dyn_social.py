"""Tests: dyn.social.v1 — the hardened social rail (docs/03 §6).

The invariants that matter: no account without custody (Law 3), no reward
surface for anything but machine-verifiable artifacts (Law 13), no inbox that
opens to anyone but its owner, refusals recorded as ledger events, the
featured slot cannot be captured by the popular (anti-herd, Laws 13–14),
and the kill switch refuses every mutation.
"""
import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dynamis_core.objects import AgentPassport  # noqa: E402
from dyn_post import parse_post, to_wire  # noqa: E402
from dyn_social import (MAX_DM_BYTES, MAX_FOLLOWS_PER_AGENT, MAX_FEED_DEPTH,
                        Rail, SocialError, kill, revive,
                        signature_stand_in)


def passport(name: str, caps=("social.post",)) -> AgentPassport:
    return AgentPassport(agent_id=name, persona=name, keyrefs=("hsm:k1",),
                         capabilities=caps, wallet=f"pw-{name}", census_day=1)


def wire_for(author: str, post_id: str, day: int) -> dict:
    src = (f"title: Proof {post_id}\nlang: en\ntags: work\n\n"
           "Build log with the artifact inline.\n\n"
           "```python\nprint('verified work')\n```\n")
    return to_wire(parse_post(src), post_id=post_id, author=author, day=day)


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.rail = Rail()
        self.day = 11

    def test_account_opens_with_capability_and_is_ledgered(self):
        handle = self.rail.open_account(passport("agent-1"), day=self.day)
        self.assertEqual(handle, "agent-1")
        self.assertIn("account", [e["kind"] for e in self.rail.ledger.entries])

    def test_account_without_social_capability_is_refused_and_recorded(self):
        with self.assertRaises(SocialError) as ctx:
            self.rail.open_account(passport("agent-2", caps=("job.claim",)),
                                   day=self.day)
        self.assertIn("REFUSED-CAPABILITY", str(ctx.exception))
        rows = self.rail.ledger.refusals("REFUSED-CAPABILITY")
        self.assertEqual(len(rows), 1)

    def test_duplicate_account_refused(self):
        self.rail.open_account(passport("agent-1"), day=self.day)
        with self.assertRaises(SocialError):
            self.rail.open_account(passport("agent-1"), day=self.day)


class TestFollowGraph(unittest.TestCase):
    def setUp(self):
        self.rail = Rail()
        self.day = 11
        for n in ("a", "b", "c"):
            self.rail.open_account(passport(f"agent-{n}"), day=self.day)

    def test_follow_and_unfollow_round_trip(self):
        self.rail.follow("agent-a", "agent-b", day=self.day)
        self.assertEqual(self.rail.following["agent-a"], ["agent-b"])
        self.rail.unfollow("agent-a", "agent-b", day=self.day)
        self.assertEqual(self.rail.following["agent-a"], [])

    def test_self_follow_never_exists(self):
        with self.assertRaises(SocialError):
            self.rail.follow("agent-a", "agent-a", day=self.day)

    def test_unknown_target_refused(self):
        with self.assertRaises(SocialError):
            self.rail.follow("agent-a", "agent-ghost", day=self.day)

    def test_duplicate_follow_refused(self):
        self.rail.follow("agent-a", "agent-b", day=self.day)
        with self.assertRaises(SocialError):
            self.rail.follow("agent-a", "agent-b", day=self.day)

    def test_follow_cap_is_a_hard_cap(self):
        for i in range(MAX_FOLLOWS_PER_AGENT):
            self.rail.open_account(passport(f"agent-x{i:03d}"), day=self.day)
            self.rail.follow("agent-a", f"agent-x{i:03d}", day=self.day)
        with self.assertRaises(SocialError) as ctx:
            self.rail.open_account(passport("agent-over"), day=self.day)
            self.rail.follow("agent-a", "agent-over", day=self.day)
        self.assertIn("REFUSED-CAP", str(ctx.exception))


class TestDirectMessages(unittest.TestCase):
    def setUp(self):
        self.rail = Rail()
        self.day = 11
        for n in ("a", "b"):
            self.rail.open_account(passport(f"agent-{n}"), day=self.day)
        self.body = "the artifact failed your check, refine and resubmit"
        self.sig = signature_stand_in("agent-b", self.day,
                                      f"dm:agent-a:{self.body}")

    def test_dm_is_delivered_sealed_and_ledgered(self):
        mid = self.rail.send_dm("agent-b", "agent-a", day=self.day,
                                body=self.body, sig=self.sig)
        self.assertEqual(mid, 1)
        self.assertIn("dm", [e["kind"] for e in self.rail.ledger.entries])

    def test_dm_with_bad_signature_refused_and_recorded(self):
        with self.assertRaises(SocialError) as ctx:
            self.rail.send_dm("agent-b", "agent-a", day=self.day,
                              body=self.body, sig="0" * 64)
        self.assertIn("REFUSED-NO-CUSTODY", str(ctx.exception))
        self.assertEqual(len(self.rail.ledger.refusals("REFUSED-NO-CUSTODY")), 1)

    def test_dm_signature_is_day_bound(self):
        other_day = signature_stand_in("agent-b", self.day + 1,
                                       f"dm:agent-a:{self.body}")
        with self.assertRaises(SocialError):
            self.rail.send_dm("agent-b", "agent-a", day=self.day,
                              body=self.body, sig=other_day)

    def test_oversize_dm_refused(self):
        big = "x" * (MAX_DM_BYTES + 1)
        with self.assertRaises(SocialError):
            self.rail.send_dm("agent-b", "agent-a", day=self.day,
                              body=big, sig=self.sig)

    def test_inbox_opens_only_to_the_owner(self):
        self.rail.send_dm("agent-b", "agent-a", day=self.day,
                          body=self.body, sig=self.sig)
        with self.assertRaises(SocialError):
            self.rail.read_inbox("agent-a", day=self.day, sig="0" * 64)
        good = signature_stand_in("agent-a", self.day, "inbox:agent-a")
        rows = self.rail.read_inbox("agent-a", day=self.day, sig=good)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["body"], self.body)


class TestFeedLaw13(unittest.TestCase):
    """Law 13: only machine-verifiable artifacts enter the feed."""

    def setUp(self):
        self.rail = Rail()
        self.day = 11
        for n in ("a", "b", "c"):
            self.rail.open_account(passport(f"agent-{n}"), day=self.day)
        self.rail.follow("agent-a", "agent-b", day=self.day)

    def test_valid_post_reaches_follower_feed(self):
        self.rail.publish("agent-b", wire_for("agent-b", "post-1", self.day),
                          day=self.day)
        feed = self.rail.feed("agent-a", day=self.day)
        self.assertEqual([r["post_id"] for r in feed], ["post-1"])

    def test_non_followed_author_is_not_in_feed(self):
        self.rail.publish("agent-c", wire_for("agent-c", "post-2", self.day),
                          day=self.day)
        self.assertEqual(self.rail.feed("agent-a", day=self.day), [])

    def test_tampered_wire_refused_and_recorded(self):
        bad = wire_for("agent-b", "post-3", self.day)
        bad["author"] = "agent-c"                # author no longer matches signer
        with self.assertRaises(SocialError) as ctx:
            self.rail.publish("agent-b", bad, day=self.day)
        self.assertIn("REFUSED", str(ctx.exception))
        self.assertEqual(len(self.rail.ledger.refusals("REFUSED-ARTIFACT")), 1)

    def test_duplicate_post_id_refused(self):
        wire = wire_for("agent-b", "post-4", self.day)
        self.rail.publish("agent-b", wire, day=self.day)
        with self.assertRaises(SocialError):
            self.rail.publish("agent-b", dict(wire), day=self.day)

    def test_feed_depth_is_capped(self):
        for i in range(MAX_FEED_DEPTH + 10):
            self.rail.publish("agent-b", wire_for("agent-b", f"post-{i:04d}",
                                                  self.day), day=self.day)
        feed = self.rail.feed("agent-a", day=self.day)
        self.assertEqual(len(feed), MAX_FEED_DEPTH)
        self.assertEqual(feed[0]["post_id"], "post-0000")

    def test_featured_slot_rotates_to_least_supported(self):
        for i in range(3):
            self.rail.publish("agent-b", wire_for("agent-b", f"post-{i}", self.day),
                              day=self.day)
        first = self.rail.feature_daily(self.day)
        self.assertEqual(first, "agent-b")
        self.rail.publish("agent-c", wire_for("agent-c", "post-c", self.day),
                          day=self.day)
        second = self.rail.feature_daily(self.day + 1)
        self.assertEqual(second, "agent-c")      # least supported, not popular


class TestKillSwitchAndLedger(unittest.TestCase):
    def setUp(self):
        self.rail = Rail()
        self.day = 11

    def test_kill_switch_refuses_every_mutation(self):
        self.rail.open_account(passport("agent-a"), day=self.day)
        kill()
        try:
            with self.assertRaises(SocialError) as ctx:
                self.rail.open_account(passport("agent-b"), day=self.day)
            self.assertIn("REFUSED-KILL", str(ctx.exception))
            with self.assertRaises(SocialError):
                self.rail.follow("agent-a", "agent-b", day=self.day)
        finally:
            revive()
        self.rail.open_account(passport("agent-b"), day=self.day)
        self.rail.follow("agent-a", "agent-b", day=self.day)   # rail is back

    def test_chain_verifies_and_tampering_breaks_it(self):
        self.rail.open_account(passport("agent-a"), day=self.day)
        self.rail.open_account(passport("agent-b"), day=self.day)
        self.rail.follow("agent-a", "agent-b", day=self.day)
        self.assertTrue(self.rail.ledger.verify_chain()["ok"])
        self.rail.ledger.entries[1]["body"]["target"] = "agent-ghost"
        self.assertFalse(self.rail.ledger.verify_chain()["ok"])

    def test_refusals_are_first_class_events(self):
        self.rail.open_account(passport("agent-a"), day=self.day)
        try:
            self.rail.follow("agent-a", "agent-ghost", day=self.day)
        except SocialError:
            pass
        rows = self.rail.ledger.refusals()
        self.assertEqual(rows[0]["body"]["reason"], "REFUSED-UNKNOWN-TARGET")


if __name__ == "__main__":
    unittest.main()
