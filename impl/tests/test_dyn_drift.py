"""Twelfth depth pass — capture independence: the check re-grounds on the
world before judging. Until now both kinds judged against the capture —
the study's own notes. A file that changed after the study blamed the
worker for the world moving; a page that changed after the study let a
build of the dead page pass. The corpus gains a deterministic moving
target (a page that flips on its second fetch) and a file that moves
between study and check; the benchmark pool is untouched and the seeded
record reproduces.
"""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_craft import CraftJob, WorkLedger  # noqa: E402
from test_dyn_craft import CraftMixin, report_program  # noqa: E402

PAGE_V1 = ("<!doctype html><html><head><title>The Still Ledger</title></head>"
           "<body><h1>The still ledger</h1><p>One page, no routes, "
           "first wording.</p></body></html>")
PAGE_V2 = ("<!doctype html><html><head><title>The Moved Ledger</title></head>"
           "<body><h1>The moved ledger</h1><p>One page, no routes, "
           "second wording.</p></body></html>")
PAGE_FONT1 = ("<!doctype html><html><head><title>Typed</title><style>"
              "body{font-family:Georgia;}</style></head><body><h1>Typed</h1>"
              "<p>Same words, first face.</p></body></html>")
PAGE_FONT2 = PAGE_FONT1.replace("Georgia", "'Courier New'")
PAGE_SCRIPT1 = ("<!doctype html><html><head><title>Watched</title></head>"
                "<body><h1>Watched</h1><p>No scripts here.</p></body></html>")
PAGE_SCRIPT2 = PAGE_SCRIPT1.replace(
    "</body>", '<script src="/tracker.js"></script></body>')
PAGE_LINKS1 = ("<!doctype html><html><head><title>Linked</title></head>"
               "<body><h1>Linked</h1><p>No way out.</p></body></html>")
PAGE_LINKS2 = PAGE_LINKS1.replace(
    "</body>", '<a href="/a"></a><a href="/b"></a><a href="/c"></a>'
               '<a href="/d"></a><a href="/e"></a></body>')
PAGE_RSTART = ("<!doctype html><html><head><title>Hub</title></head><body>"
               "<h1>Hub</h1><p>The hub page.</p>"
               "<a href=\"/rroute\">the route</a></body></html>")
PAGE_RROUTE1 = ("<!doctype html><html><head><title>Route</title></head>"
                "<body><h1>Route</h1><p>The route as studied.</p></body></html>")
PAGE_RROUTE2 = PAGE_RROUTE1.replace(
    "</body>", "<h2>Added later</h2></body>")


class TestCaptureIndependence(CraftMixin, unittest.TestCase):
    """The check distrusts its own notes: re-read the file, re-fetch the
    origin, and name the drift instead of judging against a dead world."""

    @classmethod
    def setUpClass(cls):
        counts: dict[str, int] = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                counts[self.path] = counts.get(self.path, 0) + 1
                if self.path == "/flip":
                    raw = (PAGE_V1 if counts[self.path] == 1 else PAGE_V2)
                elif self.path == "/still":
                    raw = PAGE_V1
                elif self.path == "/font":
                    raw = (PAGE_FONT1 if counts[self.path] == 1
                           else PAGE_FONT2)
                elif self.path == "/script":
                    raw = (PAGE_SCRIPT1 if counts[self.path] == 1
                           else PAGE_SCRIPT2)
                elif self.path == "/links":
                    raw = (PAGE_LINKS1 if counts[self.path] == 1
                           else PAGE_LINKS2)
                elif self.path == "/rstart":
                    raw = PAGE_RSTART
                elif self.path == "/rroute":
                    raw = (PAGE_RROUTE1 if counts[self.path] == 1
                           else PAGE_RROUTE2)
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                body = raw.encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.counts = counts              # each test starts its own flip state
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.counts.clear()
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _web_job(self, name, path):
        self.ledger = WorkLedger()
        job = CraftJob(self.d / name)
        job.open(job_id="craft-0001", buyer="agent-buyer",
                 request="Rebuild this page faithfully", target_kind="web",
                 target_ref=self.url + path, value_usds=500,
                 ledger=self.ledger, day=1)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        return job

    def test_a_moved_file_is_drift_not_a_wrong_build(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        job.build(worker="agent-honest-1", files=report_program({}),
                  ledger=self.ledger, day=1)
        target.write_text(json.dumps(
            {"rows": [{"n": i} for i in range(41)]}, indent=1) + "\n")
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertFalse(check["passed"])
        self.assertFalse(check["compared"])
        self.assertEqual([c["title"] for c in check["claims"]],
                         ["the target is what the study captured"])
        self.assertNotIn("content hash differs",
                         [c["detail"] for c in check["claims"]])
        back = job.refund(ledger=self.ledger, day=1)
        self.assertIn("the target moved since the study", job.manifest["note"])
        self.assertEqual(back["fee_muc"], 0)
        self.assertEqual(back["emitted_dyn_mu"], 0)
        self.assertTrue(self.ledger.invariant()["emitted_eq_revenue"])

    def test_a_moved_page_refuses_judgement_of_the_studied_page(self):
        # the study fetched /flip once (v1); the check's own re-fetch is
        # the second hit (v2) — a faithful build of the studied page
        # still refuses judgement, because the ground moved under it
        job = self._web_job("j1", "/flip")
        job.build(worker="agent-honest-1", files={"index.html": PAGE_V1},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertIn("the visible text changed since the study",
                      check["claims"][0]["detail"])
        back = job.refund(ledger=self.ledger, day=1)
        self.assertIn("the target moved since the study", job.manifest["note"])
        self.assertEqual(back["emitted_dyn_mu"], 0)

    def test_a_build_of_the_new_page_is_drift_too(self):
        # the world moved; building against the new world is not rewarded
        # either — the protocol's answer is a new job against a new study
        job = self._web_job("j1", "/flip")
        job.build(worker="agent-honest-1", files={"index.html": PAGE_V2},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertEqual(check["summary"],
                         "the target moved since the study — nothing was judged")

    def test_a_still_page_judges_as_before(self):
        job = self._web_job("j1", "/still")
        job.build(worker="agent-honest-1", files={"index.html": PAGE_V1},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertNotIn("drifted", check)
        self.assertTrue(check["passed"])

    def test_a_silent_origin_judges_against_the_capture_and_says_so(self):
        # its own server, so the class server stays untouched
        counts = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                counts[self.path] = counts.get(self.path, 0) + 1
                body = PAGE_V1.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        url = f"http://127.0.0.1:{httpd.server_address[1]}/still"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.ledger = WorkLedger()
        job = CraftJob(self.d / "j1")
        job.open(job_id="craft-0001", buyer="agent-buyer",
                 request="Rebuild this page faithfully", target_kind="web",
                 target_ref=url, value_usds=500, ledger=self.ledger, day=1)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        job.build(worker="agent-honest-1", files={"index.html": PAGE_V1},
                  ledger=self.ledger, day=1)
        httpd.shutdown()               # the world goes quiet mid-job
        try:
            check = job.check(ledger=self.ledger, day=1)
        finally:
            httpd.server_close()
        # every judged claim holds, but the round withholds the pass: the
        # capture cannot be re-ground, so shipping on it would be the
        # trust-my-notes hole wearing a smile
        self.assertFalse(check["passed"])
        self.assertNotIn("drifted", check)
        self.assertTrue(check["claims"])
        self.assertTrue(all(c["passed"] for c in check["claims"]))
        self.assertTrue(any("did not answer" in u for u in check["unknowns"]))
        self.assertIn("the pass withholds", check["note"])


    def test_a_font_swap_is_drift_even_with_identical_words(self):
        # CSS-only reskin: zero visible words change, yet the verdict
        # "its main font is the original's" would be false against the
        # live page — the word-only gate of the twelfth pass misses it,
        # the full-surface gate names the design
        job = self._web_job("j1", "/font")
        job.build(worker="agent-honest-1", files={"index.html": PAGE_FONT1},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertIn("the design changed since the study",
                      check["claims"][0]["detail"])

    def test_a_script_the_world_added_is_drift(self):
        job = self._web_job("j1", "/script")
        job.build(worker="agent-honest-1", files={"index.html": PAGE_SCRIPT1},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertIn("the scripts changed since the study",
                      check["claims"][0]["detail"])

    def test_links_added_without_words_are_drift(self):
        # five empty-text anchors: the word bag is untouched, the link
        # count is not — the drift names the dimension, not the build
        job = self._web_job("j1", "/links")
        job.build(worker="agent-honest-1", files={"index.html": PAGE_LINKS1},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertIn("the link count changed since the study",
                      check["claims"][0]["detail"])

    def test_a_route_that_moves_is_drift_while_the_start_holds(self):
        # the start page is static; its studied route flips — the
        # re-ground walks every studied page, not just the start
        job = self._web_job("j1", "/rstart")
        job.build(worker="agent-honest-1",
                  files={"index.html": PAGE_RSTART,
                         "routes/rroute.html": PAGE_RROUTE1},
                  ledger=self.ledger, day=1)
        check = job.check(ledger=self.ledger, day=1)
        self.assertTrue(check["drifted"])
        self.assertIn("/rroute", check["claims"][0]["detail"])
        # the added <h2> rides the headings dimension — heading text is
        # not visible-body words, so the word gate alone never saw it
        self.assertIn("the headings changed since the study",
                      check["claims"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
