"""dyn.console.v1 — the console serves the fleet read-only, and only read-only."""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_console import CONSOLE, Console, demo_fleet, make_handler  # noqa: E402
from dyn_fleet import consolidated_view  # noqa: E402


class TestConsole(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.console = Console(demo_fleet())
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        make_handler(cls.console))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path: str):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read()

    def test_health(self):
        st, body = self.get("/health")
        self.assertEqual(st, 200)
        d = json.loads(body)
        self.assertTrue(d["ok"] and d["read_only"])
        self.assertEqual(d["protocol"], CONSOLE)

    def test_served_view_equals_the_fleet(self):
        st, body = self.get("/view.json")
        self.assertEqual(st, 200)
        served = json.loads(body)
        direct = consolidated_view(self.console.entities)
        self.assertEqual(served["rollup_digest"], direct["rollup_digest"])
        self.assertEqual(served["entities"], 3)
        self.assertTrue(served["all_balanced"])

    def test_html_names_the_digest(self):
        st, body = self.get("/")
        self.assertEqual(st, 200)
        text = body.decode("utf-8")
        self.assertIn("read-only", text)
        self.assertIn(self.console.view()["rollup_digest"], text)

    def test_write_methods_refused(self):
        for method in ("POST", "PUT", "DELETE"):
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/view.json",
                data=b"{}", method=method)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(cm.exception.code, 405, method)
            self.assertIn(b"read-only by construction", cm.exception.read())

    def test_unknown_route_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/no/such/route")
        self.assertEqual(cm.exception.code, 404)

    def test_read_only_proof_holds_after_serving(self):
        """Every request re-asserts the startup digests — serving moved nothing."""
        self.console.view()                    # raises if a digest moved
        digests = {e.entity_id: e.book.journal_digest()
                   for e in self.console.entities}
        self.assertEqual(digests, self.console.digests_at_start)


if __name__ == "__main__":
    unittest.main()
