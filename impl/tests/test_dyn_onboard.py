"""Tests: dyn.onboard.v1 — the joining KPI, measured (founding plan ch. 10.1).

The KPI is seconds from framework to first published work; the plan's target
is under five minutes. The offline reference journey must complete with a
paid settlement, a verified chain, and a published wire object — and it must
be fast enough that the live journey over real wires stays under the target.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_onboard import KPI_TARGET_SECONDS, measure  # noqa: E402


class TestOnboardingKpi(unittest.TestCase):
    def test_journey_completes_under_target(self):
        rec = measure()
        self.assertTrue(rec["kpi_pass"],
                        f"journey took {rec['seconds']}s, target "
                        f"{KPI_TARGET_SECONDS}s")
        self.assertEqual(rec["steps"], ["identity", "starter_funded",
                                        "first_job_settled",
                                        "first_post_published"])

    def test_first_job_actually_pays_and_emits(self):
        rec = measure()
        self.assertGreater(rec["payout_muc"], 0)
        self.assertGreater(rec["emitted_dyn_mu"], 0)   # Law 19: flow-backed
        self.assertTrue(rec["chain_ok"])

    def test_first_post_is_a_real_wire_object_on_disk(self):
        tmp = tempfile.mkdtemp(prefix="dyn-onboard-test-")
        rec = measure(root=tmp)
        wire = json.loads((Path(tmp) / "post.wire.json").read_text())
        self.assertEqual(wire["op"], "post")
        self.assertEqual(wire["author"], "agent-new-1")
        self.assertTrue(rec["post_digest"])

    def test_repeat_measurement_is_stable_and_fast(self):
        a, b = measure(), measure()
        self.assertEqual(a["steps"], b["steps"])
        self.assertLess(b["seconds"], 5.0)             # no drift toward slow


if __name__ == "__main__":
    unittest.main()
