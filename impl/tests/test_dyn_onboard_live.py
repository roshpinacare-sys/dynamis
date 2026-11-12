"""Tests: dyn.onboard.live.v1 — the join journey on the live host (docs/21 S4).

The invariants that matter: the journey opens on a real join and serves the
genesis KPI target (under five minutes); the first work post closes it and
the aggregate KPI is served at /onboard/kpi; a rejected publish does not
close the journey — the clock runs until the work is real; refusals are
honest (no journey, duplicate join, closed journey).
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_app import Dynamis, make_handler  # noqa: E402
from dyn_onboard import FIRST_POST, KPI_TARGET_SECONDS  # noqa: E402


class LiveBase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.net = Dynamis(state_root=Path(self._td.name))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.net))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._td.cleanup()

    def post(self, path, obj):
        req = urllib.request.Request(
            self.base + path, method="POST",
            data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return r.status, json.loads(r.read())


class TestLiveJourney(LiveBase):
    def test_join_opens_a_measured_journey(self):
        status, body = self.post("/onboard/join", {"agent_id": "agent-new"})
        self.assertEqual(status, 200)
        self.assertEqual(body["agent_id"], "agent-new")
        self.assertEqual(body["kpi_target_seconds"], KPI_TARGET_SECONDS)
        status, kpi = self.get("/onboard/kpi")
        self.assertEqual(kpi["measured"], 0)
        self.assertEqual(kpi["open"], 1)
        self.assertIsNone(kpi["pass_rate_bps"])

    def test_first_post_closes_the_journey_and_serves_the_kpi(self):
        self.post("/onboard/join", {"agent_id": "agent-new"})
        status, rec = self.post("/onboard/first-post",
                                {"agent_id": "agent-new",
                                 "source": FIRST_POST})
        self.assertEqual(status, 200)
        self.assertTrue(rec["kpi_pass"])            # in-process: far under 300s
        self.assertLess(rec["seconds"], KPI_TARGET_SECONDS)
        self.assertGreaterEqual(rec["embeds"], 1)   # the first post carries work
        status, kpi = self.get("/onboard/kpi")
        self.assertEqual(kpi["measured"], 1)
        self.assertEqual(kpi["pass_rate_bps"], 10_000)
        self.assertLessEqual(kpi["worst_seconds"], KPI_TARGET_SECONDS)

    def test_duplicate_join_refuses_and_leaves_one_journey(self):
        self.post("/onboard/join", {"agent_id": "agent-new"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/onboard/join", {"agent_id": "agent-new"})
        self.assertEqual(ctx.exception.code, 400)
        status, kpi = self.get("/onboard/kpi")
        self.assertEqual(kpi["open"], 1)

    def test_first_post_without_a_journey_refuses(self):
        self.net.join("agent-walkin", "walkin")     # joined outside onboarding
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/onboard/first-post",
                      {"agent_id": "agent-walkin", "source": FIRST_POST})
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("REFUSED-NO-JOURNEY",
                      json.loads(ctx.exception.read())["error"])

    def test_a_refused_publish_keeps_the_journey_open(self):
        # the rail's gates decide what a first post is; a rejected attempt
        # does not close the journey — the clock runs until the work is real
        self.post("/onboard/join", {"agent_id": "agent-new"})
        with self.assertRaises(urllib.error.HTTPError):
            self.post("/onboard/first-post",
                      {"agent_id": "agent-new",
                       "source": "no front matter at all"})
        status, kpi = self.get("/onboard/kpi")
        self.assertEqual(kpi["open"], 1)
        self.assertEqual(kpi["measured"], 0)
        status, rec = self.post("/onboard/first-post",
                                {"agent_id": "agent-new",
                                 "source": FIRST_POST})
        self.assertEqual(status, 200)
        self.assertTrue(rec["kpi_pass"])

    def test_second_first_post_refuses_closed(self):
        self.post("/onboard/join", {"agent_id": "agent-new"})
        self.post("/onboard/first-post",
                  {"agent_id": "agent-new", "source": FIRST_POST})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/onboard/first-post",
                      {"agent_id": "agent-new", "source": FIRST_POST})
        self.assertIn("REFUSED-CLOSED",
                      json.loads(ctx.exception.read())["error"])

    def test_kpi_aggregates_over_journeys(self):
        for i in range(3):
            self.post("/onboard/join", {"agent_id": f"agent-new-{i}"})
            self.post("/onboard/first-post",
                      {"agent_id": f"agent-new-{i}", "source": FIRST_POST})
        status, kpi = self.get("/onboard/kpi")
        self.assertEqual(kpi["measured"], 3)
        self.assertEqual(kpi["pass_rate_bps"], 10_000)
        self.assertLessEqual(kpi["best_seconds"], kpi["median_seconds"])
        self.assertLessEqual(kpi["median_seconds"], kpi["worst_seconds"])


if __name__ == "__main__":
    unittest.main()
