"""dyn.craft.v1 — the craft-anything loop, where it pays, end to end."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_craft import (CraftJob, CraftError, Evidence, alike, parse_page,  # noqa: E402
                       words)
from dyn_ledger import WorkLedger  # noqa: E402

PAGE = """<!doctype html><html><head><title>DYNAMIS Docs</title></head>
<body><h1>The work loop</h1><h2>Settlement</h2><p>Every payout moves on evidence
alone; the check harness re-runs the shipped bytes before any money moves and a
failed build refunds the escrow with zero fees and zero emission.</p>
<a href="/loop">the loop</a> <a href="/money">the money</a> <a href="/posts">posts</a>
<script>document.title="hacked";</script></body></html>"""


def report_program(facts):
    """The build for the file kind: reports the studied facts exactly."""
    code = (
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys\n"
        "raw = open(sys.argv[1], 'rb').read()\n"
        "kind = 'json' if raw[:1] in (b'{', b'[') else 'text'\n"
        f"lines = {facts['lines']}\n"
        "print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(),\n"
        "                  'bytes': len(raw), 'lines': lines, 'type': kind}))\n")
    return {"main.py": code}


class CraftMixin:
    def _approve(self, job, by="agent-buyer"):
        """The buyer answers the approval card study opened."""
        card = json.loads((job.root / "inbox" / "q-002.json").read_text())
        assert card["kind"] == "approval" and card["status"] == "open"
        return job.answer(card["id"], "approve", by=by,
                          ledger=self.ledger, day=1)

    def _open_file_job(self, root, target, max_rounds=6, good_enough=90.0):
        self.ledger = WorkLedger()
        job = CraftJob(root)
        job.open(job_id="craft-0001", buyer="agent-buyer",
                 request="A program that reports this dataset's facts",
                 target_kind="file", target_ref=str(target),
                 value_usds=500, max_rounds=max_rounds,
                 good_enough=good_enough, ledger=self.ledger, day=1)
        return job

    def _dataset(self, d):
        p = d / "dataset.json"
        p.write_text(json.dumps({"rows": [{"n": i} for i in range(40)]},
                                indent=1) + "\n")
        return p


class TestLikeness(unittest.TestCase):

    def test_dice_over_word_counts(self):
        self.assertEqual(alike(words("same words here"), words("same words here")), 100.0)
        self.assertEqual(alike(words("alpha beta"), words("gamma delta")), 0.0)
        self.assertEqual(alike({}, {}), 100.0)
        # 2 shared of 3 + 3 total: 200*2/6
        self.assertAlmostEqual(alike(words("aa bb cc"), words("aa bb dd")), 200 * 2 / 6)
        # single-character tokens are not words — the reference engine's rule
        self.assertEqual(alike(words("a b c"), words("a b d")), 100.0)

    def test_two_empty_outputs_are_alike(self):
        self.assertEqual(alike(words(""), words("  ")), 100.0)


class TestEvidence(unittest.TestCase):

    def _ev(self):
        return Evidence(operation="craft_file_inspect", subject={"kind": "file", "name": "d.json"},
                        params={"path": "/d.json"},
                        result={"bytes": 10, "lines": 2, "type": "json"},
                        summary="Inspected d.json.", confidence={"level": "high", "reason": "full read"},
                        authority={"basis": "measured"},
                        limitations=[{"code": "type-sniff", "message": "a guess"}],
                        coverage={"basis": "complete", "bytes": 10},
                        carries_target_content=True)

    def test_id_is_content_hash_and_verifies(self):
        ev = self._ev()
        self.assertTrue(ev.id.startswith("ev_"))
        self.assertTrue(ev.verify())

    def test_tamper_breaks_verification(self):
        ev = self._ev()
        ev.result["bytes"] = 11
        self.assertFalse(ev.verify())

    def test_display_only_fields_leave_the_id_alone(self):
        a, b = self._ev(), self._ev()
        b.summary = "A different summary for people."
        b.carries_target_content = False
        self.assertEqual(a.id, b.id)


class TestPage(unittest.TestCase):

    def test_parse_page_skips_script_and_counts(self):
        page = parse_page(PAGE)
        self.assertEqual(page["title"], "DYNAMIS Docs")   # script's title theft ignored
        self.assertEqual(page["headings"], ["The work loop", "Settlement"])
        self.assertEqual(len(page["links"]), 3)
        self.assertIn("evidence", page["text"])
        self.assertNotIn("hacked", page["text"])


class TestCraftLoop(CraftMixin, unittest.TestCase):

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_open_names_the_escrow_and_refuses_bad_kinds(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        self.assertEqual(job.manifest["escrow_usds_muc"], 500_000_000)
        self.assertEqual(job.manifest["rounds"]["max"], 6)
        self.assertEqual(job.manifest["good_enough"], 90.0)
        with self.assertRaises(CraftError):
            job.open(job_id="x", buyer="b", request="r", target_kind="repo",
                     target_ref="x", value_usds=1, ledger=self.ledger, day=1)
        with self.assertRaises(CraftError):
            self._open_file_job(self.d / "j2", target, good_enough=101)

    def test_the_loop_refuses_to_skip_steps(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        with self.assertRaises(CraftError):        # check before study/build
            job.check(ledger=self.ledger, day=1)
        with self.assertRaises(CraftError):        # settle before everything
            job.settle(ledger=self.ledger, day=1)

    def test_file_study_records_verifiable_evidence_and_inbox(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        r = job.study(ledger=self.ledger, day=1)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        self.assertEqual(facts["type"], "json")
        self.assertEqual(facts["structure"]["top_level_type"], "dict")
        self.assertEqual(len(r["evidence"]), 1)
        self.assertTrue(r["unknowns"])                     # the sniff is a guess, on the record
        self.assertTrue((self.d / "j1" / "inbox" / "q-001.json").is_file())
        self.assertTrue((self.d / "j1" / "capture" / "README.md").is_file())
        ev_path = next((self.d / "j1" / "evidence").glob("*.json"))
        ev = json.loads(ev_path.read_text())
        self.assertTrue(ev["carries_target_content"])

    def test_file_loop_settles_for_real(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        result = job.check(ledger=self.ledger, day=1)
        self.assertTrue(result["passed"])
        self.assertEqual(result["similarity_milli"], 1000)
        self.assertEqual(len(result["claims"]), 5)
        settle = job.settle(ledger=self.ledger, day=1)
        self.assertGreater(settle["payout_muc"], 0)
        self.assertTrue(settle["chain_ok"])
        inv = self.ledger.invariant()
        self.assertEqual(inv["emitted_dyn_mu"], inv["settled_usds_muc"] * 400)
        wire = job.post(day=1)
        self.assertGreaterEqual(len(wire["embeds"]), 1)
        self.assertEqual(job.manifest["status"], "settled")

    def test_fail_path_refunds_with_zero_emission(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        bad = report_program(facts)
        bad["main.py"] = bad["main.py"].replace("len(raw)", "len(raw) + 1")
        job.build(worker="agent-worker", files=bad, ledger=self.ledger, day=1)
        result = job.check(ledger=self.ledger, day=1)
        self.assertFalse(result["passed"])
        self.assertFalse(result["claims"][1]["passed"])
        back = job.refund(ledger=self.ledger, day=1)
        self.assertEqual(back["escrow_back_muc"], 500_000_000)
        self.assertEqual(back["emitted_dyn_mu"], 0)
        inv = self.ledger.invariant()
        self.assertEqual(inv["settled_usds_muc"], 0)

    def test_refine_rounds_fix_a_build_and_carry_the_count(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        bad = report_program(facts)
        bad["main.py"] = bad["main.py"].replace("len(raw)", "len(raw) + 1")
        job.build(worker="agent-worker", files=bad, ledger=self.ledger, day=1)
        self.assertFalse(job.check(ledger=self.ledger, day=1)["passed"])
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        self.assertTrue(job.check(ledger=self.ledger, day=1)["passed"])
        self.assertEqual(job.manifest["rounds"]["done"], 2)
        self.assertEqual(job.manifest["checks"][0]["passed"], False)
        self.assertEqual(job.manifest["checks"][1]["passed"], True)

    def test_rounds_cannot_run_forever(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target, max_rounds=1)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        bad = report_program(facts)
        bad["main.py"] = bad["main.py"].replace("len(raw)", "len(raw) + 1")
        job.build(worker="agent-worker", files=bad, ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        with self.assertRaises(CraftError):
            job.build(worker="agent-worker", files=report_program(facts),
                      ledger=self.ledger, day=1)

    def test_settle_refuses_a_failing_record(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        with self.assertRaises(CraftError):
            job.settle(ledger=self.ledger, day=1)


    def test_the_buyer_approves_before_the_build(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        with self.assertRaises(CraftError):
            job.build(worker="agent-worker", files=report_program(facts),
                      ledger=self.ledger, day=1)
        with self.assertRaises(CraftError):          # only the buyer decides
            job.answer("q-002", "approve", by="agent-worker",
                       ledger=self.ledger, day=1)
        item = self._approve(job)
        self.assertEqual(item["answered_by"], "agent-buyer")
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        kinds = [e["kind"] for e in self.ledger.entries]
        self.assertIn("approve", kinds)

    def test_a_deny_ends_the_loop_for_a_refund(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        job.answer("q-002", "deny", by="agent-buyer", ledger=self.ledger, day=1)
        self.assertEqual(job.manifest["status"], "denied")
        with self.assertRaises(CraftError):          # answered once — decisions are final
            job.answer("q-002", "approve", by="agent-buyer", ledger=self.ledger, day=1)
        back = job.refund(ledger=self.ledger, day=1)
        self.assertEqual(back["emitted_dyn_mu"], 0)
        self.assertEqual(self.ledger.invariant()["settled_usds_muc"], 0)

    def test_a_late_card_blocks_settlement(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        job.ask_approval("Scope changed: also render the dataset as CSV — approve?")
        with self.assertRaises(CraftError):
            job.settle(ledger=self.ledger, day=1)


class TestWebKind(CraftMixin, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/docs"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()
        self.job = CraftJob(self.d / "j1")
        self.job.open(job_id="craft-0002", buyer="agent-buyer",
                      request="Recreate this page's structure", target_kind="web",
                      target_ref=self.url, value_usds=500,
                      ledger=self.ledger, day=1)
        self.job.study(ledger=self.ledger, day=1)
        self._approve(self.job, by="agent-buyer")

    def tearDown(self):
        self._td.cleanup()

    def test_web_study_captures_the_measured_page(self):
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        self.assertEqual(facts["status"], 200)
        self.assertEqual(facts["title"], "DYNAMIS Docs")
        self.assertEqual(facts["link_count"], 3)
        self.assertEqual(facts["same_site_links"], 3)
        self.assertIn("no browser ran", facts["unknowns"][0])

    def test_an_honest_rebuild_passes_the_likeness_bar(self):
        # the build ships the start page and every studied route page
        files = {"index.html": PAGE}
        for rt in json.loads((self.d / "j1" / "capture" / "facts.json").read_text())["routes"]:
            files[f"routes/{rt['slug']}.html"] = PAGE
        self.job.build(worker="agent-worker", files=files,
                       ledger=self.ledger, day=1)
        result = self.job.check(ledger=self.ledger, day=1)
        self.assertTrue(result["passed"])
        self.assertEqual(result["similarity_milli"], 1000)
        self.assertEqual(len(result["pages"]), 3)
        self.assertTrue(all(pg["compared"] and pg["similarity_milli"] == 1000
                            for pg in result["pages"]))
        self.assertIn("across 4 page(s)", result["note"])

    def test_study_crawls_same_site_routes_by_the_reference_rules(self):
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        self.assertEqual([r["slug"] for r in facts["routes"]],
                         ["loop", "money", "posts"])   # dash-slugs, start page excluded
        self.assertTrue((self.d / "j1" / "capture" / "routes" / "loop.json").is_file())

    def test_a_missing_route_page_is_not_alike(self):
        self.job.build(worker="agent-worker", files={"index.html": PAGE},
                       ledger=self.ledger, day=1)
        result = self.job.check(ledger=self.ledger, day=1)
        self.assertFalse(result["passed"])
        self.assertTrue(any("/loop" in u for u in result["unknowns"]))
        exists = next(c for c in result["claims"]
                      if c["title"] == "every studied page exists in the build")
        self.assertFalse(exists["passed"])

    def test_one_failing_claim_blocks_readiness_however_alike(self):
        altered = PAGE.replace("<title>DYNAMIS Docs</title>", "<title>Something Else</title>")
        self.job.build(worker="agent-worker", files={"index.html": altered},
                       ledger=self.ledger, day=1)
        result = self.job.check(ledger=self.ledger, day=1)
        # the text is identical, so likeness is 100 — and the check still fails
        self.assertEqual(result["similarity_milli"], 1000)
        self.assertFalse(result["passed"])
        self.assertFalse(result["claims"][0]["passed"])
        self.assertIn("title", result["note"])

    def test_a_mismatched_rebuild_fails_on_words_and_links(self):
        poor = ("<!doctype html><html><head><title>Other</title></head><body>"
                "<p>Nothing here matches the studied page at all.</p></body></html>")
        self.job.build(worker="agent-worker", files={"index.html": poor},
                       ledger=self.ledger, day=1)
        result = self.job.check(ledger=self.ledger, day=1)
        self.assertFalse(result["passed"])
        failed = {c["title"] for c in result["claims"] if not c["passed"]}
        self.assertIn("its title matches the original", failed)
        self.assertTrue(any("words match" in t for t in failed))
        self.assertIn("every original heading appears in the build", failed)

    def test_no_build_is_no_comparison(self):
        self.job.manifest["status"] = "built"     # force the state, no files
        result = self.job.check(ledger=self.ledger, day=1)
        self.assertFalse(result["passed"])
        self.assertFalse(result["compared"])
        self.assertEqual(result["similarity_milli"], 0)
        self.assertIn("no app/index.html", result["note"])


RICH_PAGE = """<!doctype html><html lang="en"><head><title>Field Notes — Styled</title>
<style>
body { background: #ffffff; color: #1a1a2e; font-family: "Inter", sans-serif; }
h1 { font-size: 32px; color: #16213e; } h2 { font-size: 20px; }
footer { background: #f0f0f0; }
</style></head><body>
<header><nav><span>notes</span></nav></header>
<main><h1>The loop pays</h1><h2>Study</h2><p>escrow witness escrow witness settle</p>
<h2>Check</h2><p>claims hold one by one.</p>
<section><h3>Plans</h3><p>pricing escrow.</p></section>
<img src="logo.png" alt="logo"><img src="chart.png" alt="chart"></main>
<footer><p>(c) dyn</p></footer></body></html>"""


class TestCraftDepth(CraftMixin, unittest.TestCase):
    """The loop's process depth: the steps timeline, the builder's
    statement, atomic writes, and the file check's exact fixes."""

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()

    def tearDown(self):
        self._td.cleanup()

    def test_the_step_timeline_records_the_loop(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        steps = job.manifest["steps"]
        vocab = {"new", "inspecting", "building", "checking",
                 "needs_you", "ready", "stopped"}
        self.assertTrue(all(s["status"] in vocab for s in steps))
        self.assertEqual((steps[0]["step"], steps[0]["status"]), ("study", "new"))
        self.assertTrue(any(s["status"] == "needs_you" for s in steps))
        self.assertEqual(steps[-1]["step"], "done")

    def test_builds_record_the_builder_statement(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1,
                  statement="ported the report program to the studied shape")
        self.assertEqual(job.manifest["statements"],
                         [{"round": 1,
                           "statement": "ported the report program to the studied shape"}])

    def test_every_write_is_atomic(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        leftovers = [p for p in Path(self._td.name).rglob("*") if ".tmp" in p.name]
        self.assertEqual(leftovers, [])
        json.loads((self.d / "j1" / "craft.json").read_text())   # and intact

    def test_the_file_check_names_the_exact_field_in_its_fixes(self):
        target = self._dataset(self.d)
        job = self._open_file_job(self.d / "j1", target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        bad = report_program(facts)
        bad["main.py"] = bad["main.py"].replace("len(raw)", "len(raw) + 1")
        job.build(worker="agent-worker", files=bad, ledger=self.ledger, day=1)
        result = job.check(ledger=self.ledger, day=1)
        self.assertIn(f"the original's is {facts['bytes']}",
                      " ".join(f["message"] for f in result["fixes"]))


class TestWebDepth(CraftMixin, unittest.TestCase):
    """The check's depth layers against a styled page: the structure
    skeleton, design tokens with the ±3 colour tolerance, the a11y the
    source shows, and the fixes brief that drives a refine round."""

    @classmethod
    def setUpClass(cls):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                body = RICH_PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/rich"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()
        self._n = 0

    def tearDown(self):
        self._td.cleanup()

    def _fresh(self):
        """Each check runs on its own job — like a buyer opening a new one."""
        self._n += 1
        job = CraftJob(self.d / f"j{self._n}")
        job.open(job_id=f"craft-{self._n:04d}", buyer="agent-buyer",
                 request="Recreate this styled page", target_kind="web",
                 target_ref=self.url, value_usds=500,
                 ledger=self.ledger, day=1)
        job.study(ledger=self.ledger, day=1)
        self._approve(job, by="agent-buyer")
        return job

    def _run(self, job, files, statement=None):
        job.build(worker="agent-worker", files=files, ledger=self.ledger, day=1,
                  statement=statement)
        return job.check(ledger=self.ledger, day=1)

    @staticmethod
    def _claim(result, needle):
        return next(c for c in result["claims"] if needle in c["title"])

    def test_an_honest_styled_rebuild_passes_every_layer(self):
        result = self._run(self._fresh(), {"index.html": RICH_PAGE})
        self.assertTrue(result["passed"], result["note"])
        self.assertEqual(result["fixes"], [])
        for needle in ("structure", "colours", "main font", "alt text"):
            self.assertTrue(self._claim(result, needle)["passed"], needle)
        self.assertTrue(any("structure 100% alike" in n for n in result["notes"]))

    def test_a_missing_footer_is_named_by_the_structure_claim(self):
        broken = RICH_PAGE.replace("<footer><p>(c) dyn</p></footer>", "")
        result = self._run(self._fresh(), {"index.html": broken})
        c = self._claim(result, "structure")
        self.assertFalse(c["passed"])
        self.assertIn("a footer", c["detail"])
        self.assertIn("add a footer to the page",
                      [f["message"] for f in result["fixes"]])

    def test_missing_words_and_headings_reach_the_fixes(self):
        broken = RICH_PAGE.replace("<h2>Check</h2>", "").replace(
            "escrow witness escrow witness settle", "other words entirely")
        result = self._run(self._fresh(), {"index.html": broken})
        self.assertIn("Check", result["missing_headings"])
        self.assertIn("witness", result["missing_words"])
        self.assertIn('add the heading "Check"',
                      [f["message"] for f in result["fixes"]])

    def test_colour_tolerance_is_three_channels(self):
        near = RICH_PAGE.replace("color: #1a1a2e", "color: #1b1b2f")
        self.assertTrue(self._claim(self._run(self._fresh(), {"index.html": near}),
                                    "colours")["passed"])
        far = RICH_PAGE.replace("color: #1a1a2e", "color: #123456")
        result = self._run(self._fresh(), {"index.html": far})
        c = self._claim(result, "colours")
        self.assertFalse(c["passed"])
        self.assertIn("#1a1a2e (text)", c["detail"])
        self.assertIn("use the original colour #1a1a2e (text)",
                      [f["message"] for f in result["fixes"]])

    def test_the_main_font_claim_holds_and_fails(self):
        result = self._run(self._fresh(),
                           {"index.html": RICH_PAGE.replace('"Inter"', '"Poppins"')})
        self.assertFalse(self._claim(result, "main font")["passed"])
        self.assertIn("set the main font to Inter",
                      [f["message"] for f in result["fixes"]])

    def test_alt_and_lang_claims_judge_what_the_source_shows(self):
        broken = RICH_PAGE.replace(' alt="chart"', "").replace('<html lang="en">', "<html>")
        result = self._run(self._fresh(), {"index.html": broken})
        self.assertFalse(self._claim(result, "alt text")["passed"])
        self.assertFalse(self._claim(result, "language")["passed"])

    def test_the_fixes_brief_drives_the_refine_round(self):
        job = self._fresh()
        broken = (RICH_PAGE.replace("color: #1a1a2e", "color: #123456")
                  .replace("<h2>Check</h2>", "")
                  .replace("<footer><p>(c) dyn</p></footer>", ""))
        r1 = self._run(job, {"index.html": broken})
        self.assertFalse(r1["passed"])
        self.assertIn("biggest differences first", r1["refine_brief"])
        import re
        html_text = broken
        for f in r1["fixes"]:                    # the builder reads the brief
            if f["code"] == "palette":
                hex6 = re.search(r"#([0-9a-f]{6})", f["message"]).group(1)
                html_text = re.sub(r"color:\s*#[0-9a-fA-F]{6}", f"color: #{hex6}",
                                   html_text, count=1)
            elif f["code"] == "missing_heading":
                h = re.search(r'add the heading "(.+?)"', f["message"]).group(1)
                html_text = html_text.replace("</main>", f"<h2>{h}</h2></main>")
            elif f["code"] == "missing_part" and "footer" in f["message"]:
                html_text = html_text.replace(
                    "</body>", "<footer><p>(c) dyn</p></footer></body>")
        r2 = self._run(job, {"index.html": html_text},
                       statement="restored the footer, the Check heading and the original colour")
        self.assertTrue(r2["passed"], r2["note"])
        self.assertEqual(r2["round"], 2)
        self.assertEqual(job.manifest["statements"],
                         [{"round": 2, "statement":
                           "restored the footer, the Check heading and the original colour"}])


COUNTER_ORIG = """#!/usr/bin/env python3
import sys
data = sys.stdin.read()
print(f"counter counted {len(data.split())} words")
print("counter used dyn-craft v1")
sys.exit(0)
"""


def counter_program(report_facts, exit_code=0, garbage=False):
    """The rebuild: reports the studied facts when given a path, and mimics
    the original's runs when run with stdin."""
    tail = "" if garbage else "    print('main used dyn-craft v1')\n"
    body = ("main counted OTHER words entirely" if garbage
            else f"main counted {{len(data.split())}} words")
    return {"main.py": (
        "import hashlib, json, sys\n"
        "if len(sys.argv) > 1:\n"
        "    raw = open(sys.argv[1], 'rb').read()\n"
        "    lines = raw.count(b'\\n') + (0 if raw.endswith(b'\\n') or not raw else 1)\n"
        "    print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(),"
        " 'bytes': len(raw), 'lines': lines, 'type': 'text'}))\n"
        "else:\n"
        f"    data = sys.stdin.read()\n"
        f'    print(f"{body}")\n'
        f"{tail}"
        f"    sys.exit({exit_code})\n"
    )}


class TestCraftRuns(CraftMixin, unittest.TestCase):
    """The runs check — the reference engine's RunsCheck ported to the file
    kind: recorded sample runs, judged input by input."""

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()
        self.target = self.d / "counter.py"
        self.target.write_text(COUNTER_ORIG)

    def tearDown(self):
        self._td.cleanup()

    def _job(self, max_rounds=6):
        job = self._open_file_job(self.d / f"j{self._n if '_n' in dir(self) else 1}",
                                  self.target, max_rounds=max_rounds)
        return job

    def _opened(self, max_rounds=6):
        self._n = getattr(self, "_n", 0) + 1
        job = self._open_file_job(self.d / f"j{self._n}", self.target,
                                  max_rounds=max_rounds)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        return job

    def _run(self, job, files):
        job.build(worker="agent-worker", files=files, ledger=self.ledger, day=1)
        return job.check(ledger=self.ledger, day=1)

    def test_study_records_sample_runs(self):
        job = self._opened()
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        self.assertEqual(len(facts["runs"]), 2)
        self.assertEqual(facts["runs"][0]["name"], "no input")
        self.assertEqual(facts["runs"][0]["returncode"], 0)
        self.assertIn("counter counted 0 words", facts["runs"][0]["stdout"])
        self.assertEqual(len(list((self.d / "j1" / "evidence").glob("*.json"))), 2)

    def test_an_honest_rebuild_prints_what_the_original_prints(self):
        job = self._opened()
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        result = self._run(job, counter_program(facts))
        self.assertTrue(result["passed"], result["note"])
        exits = next(c for c in result["claims"]
                     if c["title"].startswith("with no input, it exits"))
        prints = next(c for c in result["claims"]
                      if "prints what the original prints" in c["title"])
        self.assertTrue(exits["passed"])
        self.assertTrue(prints["passed"])
        self.assertEqual(result["summary"],
                         "about 100% like the original, 9 of 9 claims hold")

    def test_a_wrong_output_is_named_by_the_runs_claim(self):
        job = self._opened()
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        result = self._run(job, counter_program(facts, garbage=True))
        prints = [c for c in result["claims"]
                  if "prints what the original prints" in c["title"]]
        self.assertTrue(any(not c["passed"] for c in prints))
        self.assertTrue(any("% of the words match" in c["detail"]
                            for c in prints if not c["passed"]))
        self.assertIn("print what the original prints",
                      " ".join(f["message"] for f in result["fixes"]))

    def test_a_different_exit_is_named_by_the_runs_claim(self):
        job = self._opened()
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        result = self._run(job, counter_program(facts, exit_code=1))
        exits = [c for c in result["claims"]
                 if c["title"].startswith("with no input, it exits")]
        self.assertFalse(exits[0]["passed"])
        self.assertIn("exits with code 1", exits[0]["detail"])
        self.assertIn("exit the way the original does",
                      " ".join(f["message"] for f in result["fixes"]))

    def test_an_empty_build_is_refused(self):
        job = self._opened()
        with self.assertRaises(CraftError) as ctx:
            job.build(worker="agent-worker", files={}, ledger=self.ledger, day=1)
        self.assertIn("#736", str(ctx.exception))

    def test_exhausted_rounds_refuse_with_remediation(self):
        job = self._opened(max_rounds=1)
        facts = json.loads((self.d / "j1" / "capture" / "facts.json").read_text())
        self.assertFalse(self._run(job, counter_program(facts, garbage=True))["passed"])
        with self.assertRaises(CraftError) as ctx:
            job.build(worker="agent-worker",
                      files=counter_program(facts), ledger=self.ledger, day=1)
        self.assertIn("isn't working yet", str(ctx.exception))
        self.assertIn("refund", str(ctx.exception))

    def test_an_unwritten_project_says_so(self):
        job = self._opened()
        job.build(worker="agent-worker",
                  files=counter_program(json.loads(
                      (self.d / "j1" / "capture" / "facts.json").read_text())),
                  ledger=self.ledger, day=1)
        import shutil
        shutil.rmtree(self.d / "j1" / "app")
        result = job.check(ledger=self.ledger, day=1)
        self.assertIn("has no files yet", result["note"])


class TestVerificationGame(CraftMixin, unittest.TestCase):
    """The witness band over the craft loop: a settle that lies gets
    overruled by fresh re-execution; nothing pays without it."""

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()
        self.target = self._dataset(self.d)
        self._n = 0

    def tearDown(self):
        self._td.cleanup()

    def _passing(self):
        self._n += 1
        job = self._open_file_job(self.d / f"g{self._n}", self.target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        facts = json.loads((self.d / f"g{self._n}" / "capture" / "facts.json").read_text())
        job.build(worker="agent-worker", files=report_program(facts),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        return job

    def test_an_honest_settle_is_verified_and_pays(self):
        job = self._passing()
        out = job.settle(ledger=self.ledger, day=1)
        self.assertEqual(out["verdict"], "paid")
        self.assertGreater(out["payout_muc"], 0)
        self.assertTrue(job.manifest["verification"]["verified"])
        self.assertIn("verified by fresh re-execution", job.manifest["note"])

    def test_a_forged_check_cannot_get_paid(self):
        job = self._open_file_job(self.d / "gf1", self.target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        job.build(worker="agent-worker", files={"main.py": "print('not json')"},
                  ledger=self.ledger, day=1)
        self.assertFalse(job.check(ledger=self.ledger, day=1)["passed"])  # honest FAIL
        m = job.manifest
        m["checks"][-1].update({"passed": True, "similarity_milli": 1000,
                                "summary": "about 100% like the original"})
        for c in m["checks"][-1]["claims"]:
            c["passed"] = True
        m["checks"][-1]["unknowns"] = []
        m["status"] = "checked_pass"
        job._save()
        out = job.settle(ledger=self.ledger, day=1)
        self.assertEqual(out["verdict"], "disputed")
        self.assertEqual(out["payout_muc"], 0)
        self.assertEqual(job.manifest["status"], "checked_fail")
        self.assertIn("overruled", job.manifest["note"])
        self.assertFalse(job.manifest["verification"]["verified"])
        self.assertIn("dispute", [e["kind"] for e in self.ledger.entries])

    def test_even_a_cosmetic_tamper_is_caught(self):
        job = self._passing()
        job.manifest["checks"][-1]["similarity_milli"] = 999
        job._save()
        out = job.settle(ledger=self.ledger, day=1)
        self.assertEqual(out["verdict"], "disputed")

    def test_the_game_is_deterministic_and_round_blind(self):
        job = self._passing()
        from dyn_witness import craft_evidence_digest, craft_reexecute
        g1 = craft_reexecute(job.root, day=1)
        g2 = craft_reexecute(job.root, day=1)
        self.assertEqual(g1["digests"], g2["digests"])
        self.assertEqual(g1["leader"], g2["leader"])
        r = job.manifest["checks"][-1]
        r2 = dict(r); r2["round"] = r["round"] + 5; r2["at_ms"] = 1
        self.assertEqual(craft_evidence_digest(r), craft_evidence_digest(r2))


class TestMeasurerCalibration(unittest.TestCase):
    """The checker gets checked: seeded mutations prove the likeness
    function is bounded, sensitive and ordered by severity."""

    PAGE = ('<!doctype html><html><head><title>Orchard Ledger</title></head><body>'
            '<h1>Orchard Ledger</h1><nav><a href="/pick">Pick</a><a href="/store">Store</a></nav>'
            '<main><h2>This week</h2><p>Apples are in season and the cider press runs at noon.</p>'
            '<p>Bring crates before Thursday; the cold store fills fast.</p></main>'
            '<footer><p>Open daily until the light goes.</p></footer></body></html>')

    def _likeness(self, text):
        from dyn_craft import alike, words
        return alike(words(self.PAGE), words(text))

    def test_mutations_are_bounded(self):
        import random
        rng = random.Random(11)
        tokens = self.PAGE.split()
        for _ in range(50):
            m = list(tokens)
            for i in rng.sample(range(len(m)), rng.randint(1, len(m) - 1)):
                m[i] = "zz"
            s = self._likeness(" ".join(m))
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 100.0)

    def test_severity_orders_the_score(self):
        import random
        rng = random.Random(3)
        tokens = self.PAGE.split()
        def mutate(frac):
            m = list(tokens)
            for i in rng.sample(range(len(m)), max(1, int(len(m) * frac))):
                m[i] = "zz"
            return " ".join(m)
        light, heavy, unrelated = (self._likeness(mutate(f)) for f in (0.1, 0.4, 1.0))
        self.assertGreater(light, heavy)
        self.assertGreater(heavy, unrelated)

    def test_one_changed_word_is_detected(self):
        tokens = self.PAGE.split()
        m = list(tokens)
        m[20] = "zz"
        self.assertLess(self._likeness(" ".join(m)), 100.0)

    def test_skeleton_score_reacts_to_structure(self):
        from dyn_craft import skeleton_score
        full = self._skeleton(self.PAGE)
        gutted = self._skeleton(
            self.PAGE.replace("<h2>This week</h2>", "").replace("</main>", "<h2></h2></main>")
            .replace("<footer><p>Open daily until the light goes.</p></footer>", ""))
        s_full, _ = skeleton_score(full, full)
        s_less, _ = skeleton_score(full, gutted)
        self.assertLess(s_less, s_full)

    @staticmethod
    def _skeleton(page):
        from dyn_craft import _Page
        p = _Page()
        p.feed(page)
        return p.skeleton


class TestDurabilityAndProofs(unittest.TestCase):
    """The record survives a torn write; a ledger entry carries an
    inclusion proof anyone can verify against the root."""

    def test_a_torn_write_cannot_corrupt_the_manifest(self):
        import tempfile, unittest.mock
        from dyn_craft import CraftJob
        from dyn_ledger import WorkLedger
        with tempfile.TemporaryDirectory() as td:
            job = CraftJob(Path(td) / "j1")
            job.open(job_id="craft-1", buyer="b", request="r", target_kind="file",
                     target_ref="/tmp/x", value_usds=10, ledger=WorkLedger(), day=1)
            before = (job.root / "craft.json").read_text()
            real = __import__("os").replace
            with unittest.mock.patch("dyn_craft.os.replace",
                                     side_effect=OSError("disk pulled")):
                with self.assertRaises(OSError):
                    job._save()
            self.assertEqual((job.root / "craft.json").read_text(), before)
            self.assertEqual(len(list(job.root.glob("craft.json.tmp*"))), 1)
            job._save()   # the retry lands
            self.assertEqual(len(list(job.root.glob("craft.json.tmp*"))), 0)
            json.loads((job.root / "craft.json").read_text())

    def test_ledger_entries_carry_verifiable_inclusion_proofs(self):
        from dyn_ledger import WorkLedger
        led = WorkLedger()
        for i in range(7):
            led.append(day=1, kind="work", job_id=f"craft-{i}", agent="w",
                       note=f"entry {i}")
        root = led.merkle_root([e["hash"] for e in led.entries])
        for e in led.entries:
            proof = led.inclusion_proof(e["seq"])
            self.assertTrue(led.verify_inclusion(e["hash"], proof, root), e["seq"])
            self.assertFalse(led.verify_inclusion(
                e["hash"][:-1] + ("0" if e["hash"][-1] != "0" else "1"),
                proof, root))


class TestTheWorkerAuction(CraftMixin, unittest.TestCase):
    """Who builds is decided, not claimed: bids while the buyer decides, a
    best-fit anti-herd award, and a build gate that binds the winner."""

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()
        self.target = self._dataset(self.d)
        self._n = 0

    def tearDown(self):
        self._td.cleanup()

    def _job_on(self, chain, name, study=True):
        """A fresh job on a GIVEN chain (the helper resets self.ledger — the
        auction spans jobs, so the chain is the point)."""
        self._n += 1
        job = CraftJob(self.d / name)
        job.open(job_id=f"craft-{name}", buyer="agent-buyer",
                 request="A program that reports this dataset's facts",
                 target_kind="file", target_ref=str(self.target),
                 value_usds=500, max_rounds=6, good_enough=90.0,
                 ledger=chain, day=1)
        if study:
            job.study(ledger=chain, day=1)
        return job

    def _bid(self, job, worker, stake, price=500_000_000):
        return job.bid(worker=worker, price_usds_muc=price,
                       stake_dyn_mu=stake, ledger=self.ledger, day=1)

    def test_bids_bind(self):
        job = self._job_on(self.ledger, "auc1")
        self._bid(job, "agent-a", stake=3_000_000)
        self._bid(job, "agent-b", stake=1_800_000, price=480_000_000)
        self.assertEqual([b["worker"] for b in job.manifest["bids"]],
                         ["agent-a", "agent-b"])
        with self.assertRaisesRegex(CraftError, "on the record once"):
            self._bid(job, "agent-a", stake=3_000_000)
        with self.assertRaisesRegex(CraftError, "above the funded escrow"):
            self._bid(job, "agent-c", stake=1_000_000, price=500_000_001)
        with self.assertRaisesRegex(CraftError, "without stake is a wish"):
            self._bid(job, "agent-c", stake=0)
        chain = self.ledger
        chain.append(day=1, kind="dispute", job_id="craft-auc1",
                     agent="agent-banned")
        with self.assertRaisesRegex(CraftError, "does not bid either"):
            self._bid(job, "agent-banned", stake=1_000_000)

    def test_the_award_is_best_fit_anti_herd(self):
        job = self._job_on(self.ledger, "auc2")
        self._bid(job, "agent-strong", stake=3_000_000)
        self._bid(job, "agent-weak", stake=1_800_000)
        self._approve(job)   # _approve uses self.ledger = the same chain
        self.assertEqual(job.manifest["award"]["worker"], "agent-strong")
        # the strong one settles honestly; fair share now flips a stake tie
        job.build(worker="agent-strong",
                  files=report_program(json.loads(
                      (job.root / "capture" / "facts.json").read_text())),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        self.assertEqual(job.settle(ledger=self.ledger, day=1)["verdict"], "paid")
        job2 = self._job_on(self.ledger, "auc3")
        self._bid(job2, "agent-strong", stake=3_000_000)
        self._bid(job2, "agent-fresh", stake=3_000_000)
        self._approve(job2)
        self.assertEqual(job2.manifest["award"]["worker"], "agent-fresh",
                         "equal stake → fair share (fewest settled builds) wins")
        job3 = self._job_on(self.ledger, "auc4")
        self._bid(job3, "agent-strong", stake=3_500_000)
        self._bid(job3, "agent-fresh", stake=3_000_000)
        self._approve(job3)
        self.assertEqual(job3.manifest["award"]["worker"], "agent-strong",
                         "stake dominates fair share")

    def test_only_the_awarded_worker_builds(self):
        job = self._job_on(self.ledger, "auc5")
        self._bid(job, "agent-winner", stake=3_000_000)
        self._bid(job, "agent-runner", stake=1_800_000)
        self._approve(job)
        with self.assertRaisesRegex(CraftError, "not the awarded worker"):
            job.build(worker="agent-runner",
                      files=report_program(json.loads(
                          (job.root / "capture" / "facts.json").read_text())),
                      ledger=self.ledger, day=1)
        with self.assertRaisesRegex(CraftError, "the award is on the record"):
            self._bid(job, "agent-late", stake=2_000_000)
        job.build(worker="agent-winner",
                  files=report_program(json.loads(
                      (job.root / "capture" / "facts.json").read_text())),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        out = job.settle(ledger=self.ledger, day=1)
        self.assertEqual(out["verdict"], "paid")
        self.assertEqual(job.manifest["worker"], "agent-winner")

    def test_no_bids_keeps_the_loop_open(self):
        job = self._job_on(self.ledger, "auc6")
        self._approve(job)
        self.assertNotIn("award", job.manifest)
        job.build(worker="agent-anyone",
                  files=report_program(json.loads(
                      (job.root / "capture" / "facts.json").read_text())),
                  ledger=self.ledger, day=1)
        self.assertEqual(job.manifest["worker"], "agent-anyone")

    def test_the_api_takes_bids_and_enforces_passports(self):
        import tempfile as _tf
        from dyn_app import Dynamis, AppError
        with _tf.TemporaryDirectory() as sd:
            net = Dynamis(state_root=Path(sd))
            for who in ("agent-buyer", "agent-winner", "agent-runner"):
                net.join(who, f"persona-{who}")
            net.open_craft(buyer="agent-buyer", request="auction me",
                           target_kind="file", target_ref=str(self.target))
            net.craft_study("craft-0001")
            with self.assertRaisesRegex(AppError, "no passport"):
                net.craft_bid_route("craft-0001", {"worker": "agent-ghost",
                                                   "price_usds_muc": 400_000_000,
                                                   "stake_dyn_mu": 1_000_000})
            net.craft_bid_route("craft-0001", {"worker": "agent-runner",
                                               "price_usds_muc": 480_000_000,
                                               "stake_dyn_mu": 1_800_000})
            net.craft_bid_route("craft-0001", {"worker": "agent-winner",
                                               "price_usds_muc": 500_000_000,
                                               "stake_dyn_mu": 2_500_000})
            card = next(p for p in (Path(sd) / "craft" / "craft-0001" / "inbox").glob("*.json")
                        if json.loads(p.read_text())["kind"] == "approval")
            net.craft_answer("craft-0001", card.stem, "approve", "agent-buyer")
            m = net.craft_view("craft-0001")
            self.assertEqual(m["award"]["worker"], "agent-winner")
            with self.assertRaisesRegex(CraftError, "not the awarded worker"):
                net.craft_build("craft-0001", "agent-runner", {"main.py": "x=1\n"})
            net.craft_build("craft-0001", "agent-winner",
                            report_program(json.loads(
                                (Path(sd) / "craft" / "craft-0001" / "capture" / "facts.json").read_text())))

    def test_the_mcp_bid_tool_round_trips(self):
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from dyn_mcp import h_craft_bid
        job = self._job_on(self.ledger, "auc7")
        out = h_craft_bid({"root": str(job.root), "worker": "agent-a",
                           "price_usds_muc": 450_000_000,
                           "stake_dyn_mu": 2_000_000, "day": 1})
        self.assertEqual(out["worker"], "agent-a")
        self.assertIn("sha", out)


class TestRootsTeethEyes(CraftMixin, unittest.TestCase):
    """The game gets roots (inputs bound to the buyer's pin), eyes (anyone
    can re-run it, read-only) and teeth (a caught forger cannot build)."""

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.ledger = WorkLedger()
        self.target = self._dataset(self.d)
        self._n = 0

    def tearDown(self):
        self._td.cleanup()

    def _job_through_check(self, name="rt", program=None):
        self._n += 1
        job = self._open_file_job(self.d / f"{name}{self._n}", self.target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        job.build(worker="agent-worker",
                  files=program or report_program(json.loads(
                      (job.root / "capture" / "facts.json").read_text())),
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        return job

    def test_the_approval_card_pins_the_facts(self):
        from dyn_witness import approval_facts_pin, facts_digest
        job = self._job_through_check()
        card = next(p for p in (job.root / "inbox").glob("*.json")
                    if json.loads(p.read_text())["kind"] == "approval")
        self.assertEqual(card and json.loads(card.read_text())["facts_sha"],
                         facts_digest(job.root))
        self.assertEqual(approval_facts_pin(job.root), facts_digest(job.root))

    def test_a_facts_substitution_is_disputed(self):
        job = self._job_through_check()
        self.assertTrue(job.manifest["checks"][-1]["passed"])
        facts = json.loads((job.root / "capture" / "facts.json").read_text())
        facts["substituted"] = "different target entirely"
        (job.root / "capture" / "facts.json").write_text(
            json.dumps(facts, indent=1, sort_keys=True) + "\n")
        out = job.settle(ledger=self.ledger, day=1)
        self.assertEqual(out["verdict"], "disputed")
        self.assertFalse(out["facts_ok"])
        self.assertIn("input substitution", job.manifest["note"])

    def test_the_public_verify_re_runs_the_game_read_only(self):
        import unittest.mock
        import tempfile as _tf
        from dyn_app import Dynamis
        from dyn_witness import craft_verify
        with _tf.TemporaryDirectory() as sd:
            net = Dynamis(state_root=Path(sd))
            net.join("agent-buyer", "persona-buyer")
            net.join("agent-builder", "persona-builder")
            net.open_craft(buyer="agent-buyer", request="verify me",
                           target_kind="file", target_ref=str(self.target))
            net.craft_study("craft-0001")
            card = next(p for p in (Path(sd) / "craft" / "craft-0001" / "inbox").glob("*.json")
                        if json.loads(p.read_text())["kind"] == "approval")
            net.craft_answer("craft-0001", card.stem, "approve", "agent-buyer")
            job = net._craft("craft-0001")
            job.build(worker="agent-builder",
                      files=report_program(json.loads(
                          (job.root / "capture" / "facts.json").read_text())),
                      ledger=net.ledger, day=net.day)
            net.craft_check("craft-0001")
            before = (job.root / "craft.json").read_text()
            out = net.craft_verify_route("craft-0001")
            self.assertTrue(out["verified"])
            self.assertTrue(out["facts_ok"])
            self.assertEqual((job.root / "craft.json").read_text(), before)
            # a forged record fails the same public door: the door reads the
            # record the job holds, the disk is what re-execution trusts
            net._craft("craft-0001").manifest["checks"][-1]["similarity_milli"] = 999
            out2 = net.craft_verify_route("craft-0001")
            self.assertFalse(out2["verified"])

    def test_a_caught_forger_cannot_build_again(self):
        job = self._open_file_job(self.d / "ban1", self.target)
        job.study(ledger=self.ledger, day=1)
        self._approve(job)
        job.build(worker="agent-forger", files={"main.py": "print('junk')"},
                  ledger=self.ledger, day=1)
        job.check(ledger=self.ledger, day=1)
        m = job.manifest
        m["checks"][-1].update({"passed": True, "similarity_milli": 1000,
                                "summary": "forged"})
        for c in m["checks"][-1]["claims"]:
            c["passed"] = True
        m["checks"][-1]["unknowns"] = []
        m["status"] = "checked_pass"
        job._save()
        self.assertEqual(job.settle(ledger=self.ledger, day=1)["verdict"], "disputed")
        chain = self.ledger            # the chain's ledger carries the dispute
        job2 = self._open_file_job(self.d / "ban2", self.target)
        job2.study(ledger=self.ledger, day=1)
        self._approve(job2)
        with self.assertRaisesRegex(CraftError, "dispute on the chain"):
            job2.build(worker="agent-forger", files={"main.py": "print('x')"},
                       ledger=chain, day=1)

    def test_the_mcp_verify_tool_runs_the_game(self):
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from dyn_mcp import h_craft_verify
        job = self._job_through_check(name="mv")
        out = h_craft_verify({"root": str(job.root), "day": 1})
        self.assertTrue(out["verified"])
        self.assertEqual(out["job_id"], job.manifest["job_id"])


if __name__ == "__main__":
    unittest.main()
