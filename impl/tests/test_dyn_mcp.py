"""Tests: dyn.mcp.v1 — the engine behind tool calls.

Every engine step must be reachable as one MCP tool call: initialize →
tools/list → tools/call, with the loop's refusals arriving as isError
results (information, not crashes) and the whole lifecycle drivable
through the protocol layer alone — including over real stdio.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_engine import ARTIFACT_INVOICE_PARSER  # noqa: E402
from dyn_mcp import DynamisServer, TOOLS  # noqa: E402


class TestMcpServer(unittest.TestCase):
    def setUp(self):
        self.srv = DynamisServer()
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "job-mcp-1"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    # ---------- helpers ----------
    def req(self, mid, method, params=None):
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        return self.srv.handle(msg)

    def call(self, mid, name, arguments):
        res = self.req(mid, "tools/call", {"name": name, "arguments": arguments})
        self.assertFalse(res["result"]["isError"],
                         res["result"]["content"][0]["text"])
        return json.loads(res["result"]["content"][0]["text"])

    def open_job(self):
        return self.call(10, "dyn_job_new", {
            "root": str(self.root), "job_id": "job-mcp-1",
            "value_usds": 500, "count": 500, "seed": 30161, "day": 1})

    # ---------- protocol ----------
    def test_initialize_handshake(self):
        res = self.req(1, "initialize", {"protocolVersion": "2024-11-05",
                                         "capabilities": {}})
        self.assertEqual(res["jsonrpc"], "2.0")
        self.assertEqual(res["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", res["result"]["capabilities"])
        self.assertEqual(res["result"]["serverInfo"]["name"], "dynamis")

    def test_notification_yields_no_reply(self):
        self.assertIsNone(self.srv.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_is_jsonrpc_error(self):
        res = self.req(2, "bogus/method")
        self.assertEqual(res["error"]["code"], -32601)

    def test_tools_list_exposes_seven_schematized_tools(self):
        res = self.req(3, "tools/list")
        names = [t["name"] for t in res["result"]["tools"]]
        # tools/list presents the loop in execution order, not alphabetically
        self.assertEqual(names, ["dyn_job_new", "dyn_work", "dyn_check",
                                 "dyn_settle", "dyn_refund", "dyn_post",
                                 "dyn_status"])
        self.assertEqual(set(names), set(TOOLS))
        for t in res["result"]["tools"]:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertIn("properties", t["inputSchema"])
            self.assertTrue(t["description"].strip())

    # ---------- the whole loop, through tool calls only ----------
    def test_full_lifecycle_through_tools(self):
        opened = self.open_job()
        self.assertEqual(opened["status"], "open")
        self.assertIn(opened["verification_class"], ("A", "B", "C"))

        st = self.call(11, "dyn_status", {"root": str(self.root)})
        self.assertEqual(st["status"], "open")
        self.assertEqual(st["history"], ["open"])

        art = self.tmp / "parser.py"
        art.write_text(ARTIFACT_INVOICE_PARSER)
        worked = self.call(12, "dyn_work",
                           {"root": str(self.root), "artifact": str(art)})
        # bytes on disk, not characters — the artifact carries multibyte glyphs
        self.assertEqual(worked["bytes"],
                         len(ARTIFACT_INVOICE_PARSER.encode("utf-8")))

        checked = self.call(13, "dyn_check", {"root": str(self.root), "day": 2})
        self.assertEqual(checked["overall"], "PASS")
        self.assertEqual(checked["records"], 4)

        settled = self.call(14, "dyn_settle",
                            {"root": str(self.root), "day": 10})
        self.assertGreater(settled["payout_muc"], 0)
        self.assertTrue(settled["chain_ok"])

        posted = self.call(15, "dyn_post",
                           {"root": str(self.root), "post_id": "post-mcp-001",
                            "day": 10})
        self.assertEqual(posted["embeds"], 1)

        st = self.call(16, "dyn_status", {"root": str(self.root)})
        self.assertEqual(st["status"], "settled")
        self.assertEqual(st["history"],
                         ["open", "work", "check", "settle", "post"])

    # ---------- refusals arrive as results, not crashes ----------
    def test_settle_on_open_job_is_iserror_with_status_in_message(self):
        self.open_job()
        res = self.req(20, "tools/call", {
            "name": "dyn_settle", "arguments": {"root": str(self.root)}})
        self.assertTrue(res["result"]["isError"])
        self.assertIn("status is 'open'", res["result"]["content"][0]["text"])

    def test_unknown_tool_is_iserror(self):
        res = self.req(21, "tools/call", {"name": "dyn_nope", "arguments": {}})
        self.assertTrue(res["result"]["isError"])
        self.assertIn("unknown tool", res["result"]["content"][0]["text"])

    def test_missing_arguments_are_iserror_not_traceback(self):
        res = self.req(22, "tools/call", {"name": "dyn_job_new",
                                          "arguments": {"root": "/tmp/x"}})
        self.assertTrue(res["result"]["isError"])
        self.assertIn("bad arguments", res["result"]["content"][0]["text"])

    def test_status_of_non_folder_is_readable(self):
        st = self.call(23, "dyn_status", {"root": str(self.tmp / "nothing")})
        self.assertEqual(st["status"], "not_a_job_folder")

    # ---------- real stdio: one process, newline-delimited JSON ----------
    def test_stdio_roundtrip_initialize_and_list(self):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
        proc = subprocess.run(
            [sys.executable, str(IMPL / "dyn_mcp.py")], input="\n".join(lines) + "\n",
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        replies = [json.loads(l) for l in proc.stdout.strip().splitlines()]
        self.assertEqual(len(replies), 2)           # notification stayed silent
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "dynamis")
        self.assertEqual(len(replies[1]["result"]["tools"]), 7)


if __name__ == "__main__":
    unittest.main()
