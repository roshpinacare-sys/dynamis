"""dyn.app.v1 — the network runs as one application, end to end, over HTTP."""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_app import Dynamis, make_handler  # noqa: E402
from dyn_bench import assign_tier  # noqa: E402
from dyn_engine import ARTIFACT_INVOICE_PARSER  # noqa: E402

GOOD = ARTIFACT_INVOICE_PARSER
BAD = GOOD.replace('by_currency.get(inv["currency"], 0)',
                   'by_currency.get(inv["currency"], 0) + 1')   # wrong totals


class NetMixin:
    def _net(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        net = Dynamis(state_root=Path(self._td.name))
        for i, who in enumerate(("agent-alice", "agent-bob", "agent-carol")):
            net.join(who, f"persona-{i}")
        return net

    def _settle_one_job(self, net, code):
        net.open_job(buyer="agent-alice", value_usds=500)
        net.submit_artifact("job-0001", code, "agent-bob")
        return net.check_job("job-0001")


class TestNetwork(NetMixin, unittest.TestCase):

    def setUp(self):
        self.net = self._net()

    def tearDown(self):
        self._td.cleanup()

    def test_join_creates_a_real_passport(self):
        rec = self.net.agents["agent-alice"]
        self.assertTrue(rec["keyref"].startswith("hsm:"))
        self.assertIn("social.post", rec["capabilities"])
        self.assertEqual(rec["stake_dyn_mu"], 2_500_000)
        self.assertIn("agent-alice", self.net.rail.accounts)

    def test_duplicate_join_refused(self):
        with self.assertRaises(ValueError):
            self.net.join("agent-alice", "again")

    def test_job_opens_with_locked_escrow(self):
        view = self.net.open_job(buyer="agent-alice", value_usds=500)
        self.assertEqual(view["status"], "open")
        self.assertEqual(view["escrow_usds_muc"], 500_000_000)
        self.assertEqual(view["buyer"], "agent-alice")

    def test_fraud_path_pays_zero_and_mints_zero(self):
        verdict = self._settle_one_job(self.net, BAD)
        self.assertEqual(verdict["overall"], "FAIL")
        back = self.net.refund_job("job-0001")
        self.assertEqual(back["escrow_back_muc"], 500_000_000)
        self.assertEqual(back["emitted_dyn_mu"], 0)
        self.assertEqual(back["fee_muc"], 0)
        inv = self.net.ledger.invariant()
        self.assertEqual(inv["settled_usds_muc"], 0)
        self.assertEqual(inv["emitted_dyn_mu"], 0)
        self.assertTrue(inv["emitted_eq_revenue"])
        self.assertEqual(self.net.totals["jobs_refunded"], 1)

    def test_honest_path_settles_for_real(self):
        verdict = self._settle_one_job(self.net, GOOD)
        self.assertEqual(verdict["overall"], "PASS")
        result = self.net.settle_job("job-0001")
        self.assertGreater(result["payout_muc"], 0)
        self.assertGreater(result["fee_muc"], 0)
        self.assertGreater(result["emitted_dyn_mu"], 0)
        self.assertTrue(result["chain_ok"])
        inv = self.net.ledger.invariant()
        self.assertEqual(inv["emitted_dyn_mu"],
                         inv["settled_usds_muc"] * 400)
        self.assertTrue(inv["emitted_eq_revenue"])
        rec = self.net.agents["agent-bob"]
        self.assertEqual(rec["earned_muc"], result["payout_muc"])

    def test_loop_refuses_to_skip_steps(self):
        self.net.open_job(buyer="agent-alice")
        with self.assertRaises(ValueError):        # check with no artifact
            self.net.check_job("job-0001")
        with self.assertRaises(ValueError):        # settle before check
            self.net.submit_artifact("job-0001", GOOD, "agent-bob")
            self.net.settle_job("job-0001")

    def test_publish_and_feed_carry_artifacts(self):
        src = ("title: Shipped\nlang: en\ntags: work\n\nBody.\n\n"
               "```python\nprint('real bytes')\n```\n")
        pub = self.net.publish("agent-bob", src)
        self.assertEqual(pub["embeds"], 1)
        self.net.follow("agent-alice", "agent-bob")   # the feed is the follow graph
        feed = self.net.feed("agent-alice")
        self.assertEqual(len(feed["posts"]), 1)
        self.assertIn("print", feed["posts"][0]["html"])
        self.assertIn("<pre", feed["posts"][0]["html"])

    def test_unparseable_post_refused(self):
        with self.assertRaises(ValueError):
            self.net.publish("agent-bob", "no front matter at all")

    def test_dm_sealed_to_recipient(self):
        self.net.send_dm("agent-bob", "agent-alice", "review my post")
        got = self.net.inbox("agent-alice")
        self.assertEqual(got[0]["body"], "review my post")

    def test_compute_register_allocate_settle(self):
        dev = self.net.register_device("gpu-node-1")
        self.assertEqual(dev["tier"], assign_tier(dev["throughput_us"]))
        self.assertIn("receipt_digest", dev)
        price = self.net.set_reference_price()
        self.assertGreater(price["median_muc"], 0)
        self.net.post_compute_job("cj-001", "agent-alice", erg_milli=500)
        alloc = self.net.allocate_compute()
        self.assertEqual(len(alloc["allocated"]), 1)
        self.assertEqual(alloc["allocated"][0]["device"], "gpu-node-1")
        res = self.net.settle_compute("cj-001")
        self.assertGreater(res["cost_muc"], 0)
        self.assertGreater(res["fee_muc"], 0)
        inv = self.net.ledger.invariant()
        self.assertEqual(inv["emitted_dyn_mu"], 0)   # compute mints nothing
        self.assertEqual(self.net.ledger.verify_chain()["ok"], True)

    def test_state_rollup_is_truthful(self):
        self._settle_one_job(self.net, GOOD)
        self.net.settle_job("job-0001")
        st = self.net.state()
        self.assertEqual(st["agents"], 3)
        self.assertEqual(st["job_statuses"].get("settled"), 1)
        self.assertEqual(st["chain"]["ok"], True)
        self.assertEqual(st["totals"]["jobs_settled"], 1)


class TestHTTPSurface(NetMixin, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._td = tempfile.TemporaryDirectory()
        cls.net = Dynamis(state_root=Path(cls._td.name))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.net))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls._td.cleanup()

    def call(self, path, method="GET", body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"} if body else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_serves_the_console(self):
        st, body = self.call("/")
        self.assertEqual(st, 200)
        html = body.decode("utf-8")
        self.assertIn("DYNAM", html)
        self.assertIn("dyn.app.v1", html)

    def test_health_and_state(self):
        st, body = self.call("/health")
        self.assertEqual(st, 200)
        self.assertTrue(json.loads(body)["ok"])
        st, body = self.call("/api/state")
        self.assertEqual(json.loads(body)["protocol"], "dyn.app.v1")

    def test_join_over_http(self):
        st, body = self.call("/api/agents", "POST",
                             {"agent_id": "agent-dave", "persona": "dev"})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["agent_id"], "agent-dave")
        st, _ = self.call("/api/agents", "POST",
                          {"agent_id": "agent-dave", "persona": "again"})
        self.assertEqual(st, 400)

    def test_full_job_flow_over_http(self):
        self.call("/api/agents", "POST", {"agent_id": "agent-eva"})
        st, _ = self.call("/api/jobs", "POST",
                          {"buyer": "agent-eva", "value_usds": 500})
        self.assertEqual(st, 200)
        st, body = self.call("/api/jobs/job-0001/artifact", "POST",
                             {"code": GOOD, "worker": "agent-eva"})
        self.assertEqual(st, 200)
        st, body = self.call("/api/jobs/job-0001/check", "POST", {})
        self.assertEqual(json.loads(body)["overall"], "PASS")
        st, body = self.call("/api/jobs/job-0001/settle", "POST", {})
        res = json.loads(body)
        self.assertGreater(res["payout_muc"], 0)
        self.assertTrue(res["chain_ok"])

    def test_refused_paths_are_400_with_reasons(self):
        st, body = self.call("/api/jobs/job-nope/check", "POST", {})
        self.assertEqual(st, 400)
        self.assertIn("no such job", json.loads(body)["error"])
        st, body = self.call("/api/nothing", "GET")
        self.assertEqual(st, 404)
        st, _ = self.call("/api/chain", "PUT", {})
        self.assertEqual(st, 405)


if __name__ == "__main__":
    unittest.main()
