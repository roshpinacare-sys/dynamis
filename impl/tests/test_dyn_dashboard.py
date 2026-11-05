"""Gate 2.2 — the emission dashboard: Law-19 computed, fail-closed, honest HTML."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_dashboard import DashboardError, compute, from_stream, render  # noqa: E402

RATE = 400


def row(event, **kw):
    return {"event": event, **kw}


def good_stream():
    rows = [row("open", day=1, job="j-1"), row("open", day=2, job="j-2")]
    for i, (pay, fee) in enumerate(((10_000_000, 2_000_000), (20_000_000, 4_000_000))):
        value = pay + fee
        rows.append(row("settle", day=1 + i, job=f"j-{i + 1}",
                        payout_muc=pay, fee_muc=fee, emitted_dyn_mu=value * RATE))
    rows.append(row("refund", day=3, job="j-x", emitted_dyn_mu=0))
    return rows


class TestDashboard(unittest.TestCase):

    def test_invariant_holds_on_good_stream(self):
        m = compute(good_stream())
        self.assertTrue(m["ok"])
        self.assertEqual(m["emitted_dyn_mu"], m["expected_dyn_mu"])
        self.assertEqual(m["settled_revenue_muc"], 36_000_000)
        self.assertTrue(all(m["checks"].values()))
        self.assertTrue(m["digest"])

    def test_broken_invariant_refuses_to_render(self):
        rows = good_stream()
        rows[2]["emitted_dyn_mu"] += 1            # one µ-unit of unbacked emission
        with self.assertRaises(DashboardError):
            compute(rows)

    def test_refund_with_emission_refused(self):
        rows = good_stream()
        rows[-1]["emitted_dyn_mu"] = 5
        with self.assertRaises(DashboardError):
            compute(rows)

    def test_render_shows_measured_numbers_and_gaps(self):
        m = compute(good_stream())
        html = render(m)
        self.assertIn("INVARIANT HOLDS", html)
        self.assertIn("36,000,000", html)         # measured revenue, tabular
        self.assertIn("14,400,000,000", html)     # emitted at rate 400
        self.assertIn("digest", html)
        self.assertNotIn("<script src", html)     # self-contained
        self.assertNotIn("http://", html)

    def test_from_stream_real_market_integration(self):
        """End-to-end: a real 2-day market run renders a passing dashboard."""
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            stream = Path(td) / "market.jsonl"
            out = Path(td) / "dash.html"
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent.parent / "dyn_market.py"),
                 "run", "--days", "2", "--out", str(stream)],
                check=True, capture_output=True)
            m = from_stream(stream, out)
            self.assertTrue(m["ok"])
            self.assertGreater(m["jobs_settled"], 0)
            self.assertGreater(out.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
