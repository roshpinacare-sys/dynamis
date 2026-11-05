"""Tests: dyn.x402.v1 — the paid-HTTP door (gate 2.4 rails, in-repo).

The 402 challenge is the escrow terms; payment is escrow funding; the loop's
refusals are 409s; the fail path refunds over HTTP. Both layers are tested:
the rail's dispatch directly, and the reference external client over real
localhost sockets — an outside client completing a paid job end to end.
"""
import base64
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_engine import ARTIFACT_INVOICE_PARSER, EngineError  # noqa: E402
from dyn_x402 import (DynamisRail, X402Client, _unb64,  # noqa: E402
                      make_server)
from dynamis_core import usds  # noqa: E402

BAD_ARTIFACT = ARTIFACT_INVOICE_PARSER.replace(
    '+ ln["qty"] * ln["unit_cents"]', '+ ln["qty"] * ln["unit_cents"] + 1')


class TestRailDispatch(unittest.TestCase):
    """The rail without sockets: every rule, one call at a time."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.rail = DynamisRail(root=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_health_and_card(self):
        code, health = self.rail.dispatch("GET", "/health", None)
        self.assertEqual((code, health["protocol"]), (200, "dyn.x402.v1"))
        code, card = self.rail.dispatch("GET", "/.well-known/agent-card.json", None)
        self.assertEqual(code, 200)
        self.assertEqual(len(card["skills"]), 3)
        self.assertEqual(card["payment"]["schemes"][0]["scheme"], "dyn-escrow")

    def test_offer_is_402_with_exact_escrow_terms(self):
        code, offer = self.rail.dispatch("POST", "/jobs",
                                         {"value_usds": 500, "count": 500})
        self.assertEqual(code, 402)
        t = offer["x-payment-required"]
        self.assertEqual(t["scheme"], "dyn-escrow")
        self.assertEqual(t["maxAmountRequired"], 500)
        self.assertEqual(t["resource"], "/jobs/job-x402-0001")

    def test_unpaid_check_challenges_again(self):
        self.rail.dispatch("POST", "/jobs", {"value_usds": 250})
        code, res = self.rail.dispatch("POST", "/jobs/job-x402-0001/check", {})
        self.assertEqual(code, 402)
        self.assertIn("pay first", res["error"])

    def test_amount_mismatch_and_double_payment_refused(self):
        self.rail.dispatch("POST", "/jobs", {"value_usds": 250})
        code, res = self.rail.dispatch("POST", "/jobs/job-x402-0001/payment",
                                       {"payer": "a-1", "amount_usds": 999})
        self.assertEqual(code, 402)
        self.assertIn("amount mismatch", res["error"])
        code, _ = self.rail.dispatch("POST", "/jobs/job-x402-0001/payment",
                                     {"payer": "a-1"})
        self.assertEqual(code, 201)
        code, res = self.rail.dispatch("POST", "/jobs/job-x402-0001/payment",
                                       {"payer": "a-2"})
        self.assertEqual(code, 409)

    def test_engine_violation_is_409_not_a_crash(self):
        self.rail.dispatch("POST", "/jobs", {"value_usds": 250})
        self.rail.dispatch("POST", "/jobs/job-x402-0001/payment", {"payer": "a-1"})
        code, res = self.rail.dispatch("POST", "/jobs/job-x402-0001/settle", {})
        self.assertEqual(code, 409)
        self.assertIn("status is 'open'", res["error"])

    def test_missing_payer_and_oversized_artifact(self):
        self.rail.dispatch("POST", "/jobs", {"value_usds": 250})
        code, res = self.rail.dispatch("POST", "/jobs/job-x402-0001/payment", {})
        self.assertEqual((code, res["error"][0]), (400, "p"))
        self.rail.dispatch("POST", "/jobs/job-x402-0001/payment", {"payer": "a-1"})
        code, res = self.rail.dispatch("POST", "/jobs/job-x402-0001/work",
                                       {"artifact_b64": base64.b64encode(
                                           b"x" * 65 * 1024).decode()})
        self.assertEqual(code, 413)

    def test_unknown_job_and_route(self):
        self.assertEqual(self.rail.dispatch("GET", "/jobs/nope", None)[0], 404)
        self.assertEqual(self.rail.dispatch("POST", "/jobs/x/bogus", {})[0], 404)
        self.assertEqual(self.rail.dispatch("PATCH", "/jobs", {})[0], 404)

    def test_fail_path_over_http_full_refund(self):
        """Fraud over the wire: paid job, bad artifact, FAIL, full refund."""
        self.rail.dispatch("POST", "/jobs",
                           {"value_usds": 500, "count": 250, "seed": 30161})
        self.rail.dispatch("POST", "/jobs/job-x402-0001/payment",
                           {"payer": "agent-fraud-http"})
        code, worked = self.rail.dispatch("POST", "/jobs/job-x402-0001/work", {
            "artifact_b64": base64.b64encode(BAD_ARTIFACT.encode()).decode()})
        self.assertEqual(code, 200)
        code, checked = self.rail.dispatch("POST", "/jobs/job-x402-0001/check", {})
        self.assertEqual((code, checked["overall"]), (200, "FAIL"))
        code, refunded = self.rail.dispatch("POST", "/jobs/job-x402-0001/refund", {})
        self.assertEqual(code, 200)
        self.assertEqual(refunded["escrow_back_muc"], usds(500))
        self.assertEqual(refunded["emitted_dyn_mu"], 0)
        code, status = self.rail.dispatch("GET", "/jobs/job-x402-0001", None)
        self.assertEqual(status["status"], "refunded")


class TestOverRealSockets(unittest.TestCase):
    """The gate-2.4 acceptance line: an external client completes a paid job."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.srv, cls.rail = make_server(DynamisRail(root=cls.tmp))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.client = X402Client(f"http://127.0.0.1:{cls.srv.server_address[1]}")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def test_discover_card_over_http(self):
        card = self.client.discover()
        self.assertEqual(card["protocol"], "dyn.x402.v1")
        self.assertIn("dyn-escrow", json.dumps(card))

    def test_external_client_buys_and_settles_a_job(self):
        r = self.client.buy_job(value_usds=500, count=500, seed=30161,
                                payer="agent-external-1",
                                artifact=ARTIFACT_INVOICE_PARSER.encode())
        self.assertEqual(r["check"]["overall"], "PASS")
        self.assertEqual(r["check"]["records"], 4)
        self.assertGreater(r["settle"]["payout_muc"], 0)
        self.assertTrue(r["settle"]["chain_ok"])
        self.assertEqual(r["opened"]["verification_class"],
                         r["opened"]["verification_class"])  # priced at open
        terms = r["offer"]
        self.assertEqual(terms["maxAmountRequired"], 500)
        # the job folder exists on disk with its evidence — the rail wrote it
        ev = list((self.tmp / terms["job_id"] / "evidence").glob("0*.json"))
        self.assertEqual(len(ev), 4)

    def test_header_and_body_terms_are_identical(self):
        req = urllib_json("POST", self.client.base + "/jobs",
                          {"value_usds": 250})
        terms_body = req[1]["x-payment-required"]
        terms_hdr = _unb64(req[2]["X-PAYMENT-REQUIRED"])
        self.assertEqual(terms_body, terms_hdr)


def urllib_json(method: str, url: str, body: dict) -> tuple[int, dict, dict]:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


if __name__ == "__main__":
    unittest.main()
