"""dyn_measure tests (ninth depth pass): the benchmark's own properties —
determinism, the shipping guarantee, the cost gradient, claim immunity,
and the harness fix the first benchmark run uncovered.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dyn_measure as dm  # noqa: E402


class TestWhatTheLoopChanges(unittest.TestCase):
    """One shared 12-task run; the assertions are the benchmark's contract."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._td = tempfile.TemporaryDirectory()
        cls.root = Path(cls._td.name)
        from dyn_app import Dynamis
        cls.app = Dynamis(state_root=cls.root / "state")
        for who in ("agent-buyer", "agent-honest-1", "agent-shaky-1"):
            cls.app.join(who, f"persona-{who}")
        cls.metrics = dm.run_bench(n_tasks=12, seed=20261106,
                                   root=cls.root, app=cls.app)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_the_pool_and_draws_are_deterministic(self):
        again = dm.run_bench(n_tasks=12, seed=20261106)
        for key in ("pool", "worker_model", "pipelines", "worker_income_muc",
                    "run"):
            self.assertEqual(self.metrics[key], again[key],
                             f"{key} must be a function of the seed alone")

    def test_craft_ships_no_broken_builds(self):
        model, pipes = self.metrics["worker_model"], self.metrics["pipelines"]
        self.assertGreater(model["broken_draws"], 0, "the model must draw breaks")
        self.assertEqual(pipes["craft"]["shipped_broken"], 0)
        self.assertEqual(pipes["naive"]["shipped_broken"],
                         model["broken_draws"])
        escrow = dm.VALUE_USDS * 1_000_000
        self.assertEqual(pipes["craft"]["escrow_back_muc"],
                         model["broken_draws"] * escrow,
                         "every broken delivery refunds in full")

    def test_the_cost_gradient_points_at_honesty(self):
        pipes = self.metrics["pipelines"]
        self.assertLessEqual(pipes["craft"]["cost_per_working_muc"],
                             pipes["naive"]["cost_per_working_muc"])
        income = self.metrics["worker_income_muc"]
        self.assertGreater(income["agent-honest-1"], 0)
        self.assertEqual(income["agent-shaky-1"], 0,
                         "a worker whose every build failed earns nothing")
        escrow = dm.VALUE_USDS * 1_000_000
        n = self.metrics["pool"]["tasks"]
        self.assertEqual(pipes["craft"]["buyer_paid_muc"]
                         + pipes["craft"]["escrow_back_muc"],
                         pipes["naive"]["buyer_paid_muc"],
                         pipes["naive"]["buyer_paid_muc"] == n * escrow)

    def test_a_claim_cannot_make_a_broken_build_pass(self):
        model, pipes = self.metrics["worker_model"], self.metrics["pipelines"]
        self.assertGreater(model["forged_draws"], 0)
        self.assertEqual(pipes["craft"]["forged_caught"],
                         model["forged_draws"],
                         "every forged claim met the re-executed check")
        self.assertEqual(pipes["self_report"]["forged_caught"], 0,
                         "claims gate nothing where nothing re-executes")
        self.assertEqual(pipes["self_report"]["shipped_broken"],
                         model["broken_draws"])

    def test_the_check_catches_injected_scripts(self):
        """The finding that started as a benchmark leak: scripts are
        invisible to text likeness, so the harness gives them their own
        claim — the build may carry no script the original doesn't have."""
        import http.server
        import threading
        root = self.root
        page = root / "script-target.html"
        page.write_text("<!doctype html><html><head><title>Clean Doc</title>"
                        "</head><body><h1>Clean doc</h1><p>Plain words only."
                        "</p></body></html>")
        srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            lambda *a, **k: http.server.SimpleHTTPRequestHandler(
                *a, directory=str(root), **k))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/script-target.html"
        try:
            self._script_probe(url)
        finally:
            srv.shutdown()

    def _script_probe(self, url):
        root = self.root
        page = root / "script-target.html"
        self.app.open_craft(buyer="agent-buyer", request="rebuild the clean doc",
                            target_kind="web", target_ref=url,
                            value_usds=dm.VALUE_USDS)
        jid = f"craft-{self.app._craft_seq:04d}"
        self.app.craft_study(jid)
        card = next(p for p in (root / "state" / "craft" / jid / "inbox").glob("*.json")
                    if json.loads(p.read_text())["kind"] == "approval")
        self.app.craft_answer(jid, card.stem, "approve", "agent-buyer")
        html = page.read_text()
        clean = {"index.html": html}
        hacked = {"index.html": html.replace(
            "</body>", '<script>document.title="hacked";</script></body>')}
        self.app.craft_build(jid, "agent-honest-1", hacked)
        res = self.app.craft_check(jid)
        self.assertFalse(res["passed"])
        failed = [c["title"] for c in res["claims"] if not c["passed"]]
        self.assertTrue(any("scripts" in t for t in failed), failed)
        # the faithful copy still passes — one claim, not a ban
        jid2 = f"craft-{self.app._craft_seq + 1:04d}"
        self.app.open_craft(buyer="agent-buyer", request="rebuild the clean doc",
                            target_kind="web", target_ref=url,
                            value_usds=dm.VALUE_USDS)
        self.app.craft_study(jid2)
        card2 = next(p for p in (root / "state" / "craft" / jid2 / "inbox").glob("*.json")
                     if json.loads(p.read_text())["kind"] == "approval")
        self.app.craft_answer(jid2, card2.stem, "approve", "agent-buyer")
        self.app.craft_build(jid2, "agent-honest-1", clean)
        self.assertTrue(self.app.craft_check(jid2)["passed"])

    def test_the_chain_seals_and_audits_under_load(self):
        run = self.metrics["run"]
        self.assertTrue(run["audit_ok"])
        self.assertEqual(run["seals"], run["entries"] // 12)
        self.assertGreaterEqual(run["seals"], 1)


if __name__ == "__main__":
    unittest.main()
