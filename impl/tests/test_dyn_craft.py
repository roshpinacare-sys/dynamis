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


if __name__ == "__main__":
    unittest.main()
