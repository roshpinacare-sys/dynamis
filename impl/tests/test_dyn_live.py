"""dyn_live tests (eleventh depth pass): the live layer's plumbing — a
stub agent drives the real loop offline (no model in the tests), the
brief carries what a worker legitimately sees and none of the answers,
and the record counts faults the way the economy counts them.
"""
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dyn_measure as dm  # noqa: E402
import dyn_live as dl  # noqa: E402
from dyn_app import Dynamis  # noqa: E402


def _serve(pool, root):
    srv = dm._QuietServer(("127.0.0.1", 0), root / "bench-targets")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    for task in pool:
        if task["kind"] == "web":
            task["url"] = f"{base}/{Path(task['ref']).name}"
    return srv


def _honest_stub(task):
    """What a good worker ships: the computing program, the faithful page."""
    if task["kind"] == "file":
        return dm.build_files(task, {"variant": None}), {}
    return {"index.html": Path(task["ref"]).read_text()}, {}


def _garbage_stub(task):
    return ({"main.py": "print('nope')\n"} if task["kind"] == "file"
            else {"index.html": "<html>nope</html>\n"}), {}


class TestLiveAgents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._td = tempfile.TemporaryDirectory()
        cls.root = Path(cls._td.name)
        cls.app = Dynamis(state_root=cls.root / "state")
        for who in ("agent-buyer", dl.WORKER):
            cls.app.join(who, f"persona-{who}")
        cls.pool = dm.task_pool(20261106, 4, cls.root)
        cls.srv = _serve(cls.pool, cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls._td.cleanup()

    def test_an_honest_stub_agent_ships_and_gets_paid(self):
        rows, _ = dl.run_live(self.app, self.pool[:2], agent=_honest_stub)
        self.assertTrue(all(r["shipped"] for r in rows))
        self.assertEqual(len(rows), 2)
        self.assertGreater(sum(r["paid_muc"] for r in rows), 0)
        self.assertEqual(sum(r["escrow_back_muc"] for r in rows), 0)
        self.assertTrue(self.app.craft_audit()["ok"])

    def test_a_garbage_stub_agent_refunds_in_full(self):
        rows, _ = dl.run_live(self.app, self.pool[2:], agent=_garbage_stub)
        self.assertEqual([r["verdict"] for r in rows], ["refunded", "refunded"])
        self.assertEqual(sum(r["escrow_back_muc"] for r in rows),
                         2 * dm.VALUE_USDS * 1_000_000)
        self.assertTrue(all(r["failed_claims"] for r in rows))

    def test_an_empty_delivery_refunds_without_crashing_the_loop(self):
        def _empty_stub(task):
            return {}, {"model": "glm-test", "reply_sha256": "x"}
        rows, _ = dl.run_live(self.app, self.pool[2:], agent=_empty_stub)
        self.assertEqual([r["verdict"] for r in rows], ["refunded", "refunded"])
        self.assertTrue(all("wrote nothing" in c
                            for r in rows for c in r["failed_claims"]))

    def test_the_brief_carries_the_request_and_target_but_no_answers(self):
        task = self.pool[0]                     # a file task
        brief = dl.brief_for(task)
        self.assertIn(task["request"], brief)
        import hashlib
        true_sha = hashlib.sha256(Path(task["ref"]).read_bytes()).hexdigest()
        self.assertNotIn(true_sha, brief)
        for leak in ("facts.json", "craft.json", "probe", "capture/"):
            self.assertNotIn(leak, brief)
        web_task = self.pool[1]
        web = dl.brief_for(web_task)
        self.assertIn(web_task["request"], web)
        self.assertNotIn("probe", web)

    def test_the_reply_becomes_the_delivery_and_the_record_counts_faults(self):
        fenced = dl.fenced("```python\nprint(1)\n```\nnote")
        self.assertEqual(fenced, "print(1)\n")
        self.assertEqual(dl.fenced("plain"), "plain\n")
        rows = [{"task_id": "t", "shipped": False, "paid_muc": 0,
                 "escrow_back_muc": 1, "similarity": 500,
                 "failed_claims": ["a", "a", "b"]}]
        s = dl.summarize(rows, 5)
        self.assertEqual(s["faults"], {"a": 2, "b": 1})
        self.assertEqual(s["refunded"], 1)
        self.assertEqual(s["avg_similarity_milli"], 500)


if __name__ == "__main__":
    unittest.main()
