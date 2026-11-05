"""Tests: dyn.finance.v1 — the entity book, invoices, payroll, the P&L.

The spine must close on a real market stream: escrow clears, payables settle,
the balance-sheet identity holds, and finance digests anchor into the work
ledger. Posting-level discipline first, lifecycle second, integration last.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IMPL))

from dyn_finance import (COA, BookError, EntityBook,  # noqa: E402
                         PayrollStream, WorkerRegistry, anchor_into,
                         book_from_market_stream, issue_invoice, pay_invoice,
                         report, void_invoice)
from dyn_ledger import WorkLedger  # noqa: E402
from dyn_market import Market  # noqa: E402
from dynamis_core import usds  # noqa: E402


class TestPostingDiscipline(unittest.TestCase):
    def setUp(self):
        self.book = EntityBook("ent-001")

    def test_paid_in_opens_the_book_balanced(self):
        tb = self.book.trial_balance()
        self.assertTrue(tb["balanced"])
        # signed nets: cash sits on the debit side, equity on the credit side
        self.assertEqual(tb["accounts"]["1000"], -tb["accounts"]["3000"])

    def test_posting_refuse_rules(self):
        with self.assertRaises(BookError):
            self.book.post("9999", "1000", usds(1), "unknown debit", day=1)
        with self.assertRaises(BookError):
            self.book.post("1000", "1000", usds(1), "same both sides", day=1)
        with self.assertRaises(BookError):
            self.book.post("1000", "3000", 0, "zero", day=1)
        with self.assertRaises(BookError):
            self.book.post("1000", "3000", -5, "negative", day=1)
        with self.assertRaises(BookError):
            EntityBook("BAD_ID")                       # id format enforced

    def test_journal_chain_and_tamper_detection(self):
        self.book.post("1000", "3000", usds(500), "top-up", day=1)
        self.book.post("1020", "2030", usds(250), "invoiced", day=1)
        self.assertTrue(self.book.verify_journal()["ok"])
        self.book.journal[1]["amount_muc"] = 1         # flip one entry
        self.assertFalse(self.book.verify_journal()["ok"])

    def test_journal_digest_stable(self):
        self.book.post("1000", "3000", usds(5), "x", day=1)
        self.assertEqual(self.book.journal_digest(), self.book.journal_digest())


class TestInvoiceLifecycle(unittest.TestCase):
    def setUp(self):
        self.book = EntityBook("ent-001", paid_in_muc=usds(10_000))

    def test_issue_pay_void(self):
        inv = issue_invoice(self.book, invoice_id="inv-job-1",
                            customer="cust-env-ops", value_muc=usds(500),
                            day=1, due_day=8)
        self.assertEqual(inv["total_muc"], usds(600))          # +20% markup
        tb = self.book.trial_balance()["accounts"]
        self.assertEqual(tb["1020"], usds(600))                # receivable
        self.assertEqual(tb["2030"], -usds(600))               # deferred
        pay_invoice(self.book, inv, day=2)
        tb = self.book.trial_balance()["accounts"]
        self.assertEqual(tb["1020"], 0)                        # receivable clear
        self.assertEqual(tb["1000"], usds(10_000) + usds(600))
        with self.assertRaises(BookError):
            pay_invoice(self.book, inv, day=3)                 # already paid
        inv2 = issue_invoice(self.book, invoice_id="inv-job-2",
                             customer="cust-env-ops", value_muc=usds(100),
                             day=2, due_day=9)
        void_invoice(self.book, inv2, day=3)
        self.assertEqual(inv2["status"], "void")
        self.assertEqual(self.book.trial_balance()["accounts"]["1020"], 0)

    def test_invoice_digest_binds_the_terms(self):
        inv = issue_invoice(self.book, invoice_id="inv-job-3",
                            customer="cust-env-ops", value_muc=usds(250),
                            day=1, due_day=8)
        d = inv["digest"]
        tampered = {k: v for k, v in inv.items() if k != "digest"}
        tampered["total_muc"] += 1
        import json as _json
        from dynamis_core.canonical import object_hash as _oh
        self.assertNotEqual(d, _oh(tampered))          # the digest binds terms


class TestPayroll(unittest.TestCase):
    def test_registry_and_stream(self):
        reg = WorkerRegistry()
        reg.hire("agent-honest-1", role="verified-worker",
                 rate_muc_per_day=usds(30), keyref="hsm:kr-1")
        with self.assertRaises(BookError):
            reg.hire("agent-honest-1", role="x", rate_muc_per_day=usds(1),
                     keyref="k")                               # duplicate
        with self.assertRaises(BookError):
            reg.hire("BAD!", role="x", rate_muc_per_day=usds(1), keyref="k")
        with self.assertRaises(BookError):
            reg.hire("agent-honest-2", role="x", rate_muc_per_day=0,
                     keyref="k")                               # zero salary
        book = EntityBook("ent-001", paid_in_muc=usds(10_000))
        stream = PayrollStream(book, reg, "agent-honest-1")
        accrued = stream.accrue(10, start_day=1)
        self.assertEqual(accrued, usds(300))
        self.assertEqual(book.payable("2000"), usds(300))
        self.assertEqual(book.trial_balance()["accounts"]["5010"], usds(300))
        paid = stream.pay(day=11)
        self.assertEqual(paid, usds(300))
        self.assertEqual(book.payable("2000"), 0)
        self.assertEqual(book.trial_balance()["accounts"]["1000"],
                         usds(10_000) - usds(300))
        with self.assertRaises(BookError):
            PayrollStream(book, reg, "agent-unknown")          # not hired


class TestAnchoring(unittest.TestCase):
    def test_finance_digests_ride_the_checkpoint_chain(self):
        book = EntityBook("ent-001")
        book.post("1000", "3000", usds(5), "x", day=1)
        led = WorkLedger()
        led.append(day=1, kind="settle", job_id="job-1", agent="a-1",
                   payout_muc=100, fee_muc=5, emitted_dyn_mu=42_000)
        anchor_into(led, what="ent-001:journal",
                    digest=book.journal_digest(), day=2)
        self.assertEqual(led.verify_chain()["ok"], True)
        anchors = [e for e in led.entries if e["kind"] == "anchor"]
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["body"]["digest"], book.journal_digest())
        # keep appending: the anchor rides the first checkpoint seal
        from dyn_ledger import verify_checkpoint
        for i in range(2, 15):
            led.append(day=i, kind="settle", job_id=f"job-{i}", agent="a-1",
                       payout_muc=100, fee_muc=5, emitted_dyn_mu=42_000)
        cps = led.all_checkpoints(day=15)
        self.assertTrue(cps)
        self.assertTrue(all(verify_checkpoint(c, led)["ok"] for c in cps))


class TestMeasuredPL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.market = Market(seed=3, witness=True, root=cls.tmp)
        cls.market.run(10)
        cls.rows = cls.market.stream
        cls.res = book_from_market_stream(cls.rows, days=10)
        cls.book = cls.res["book"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_books_close_and_identity_holds(self):
        tb = self.book.trial_balance()
        self.assertTrue(tb["balanced"])
        self.assertTrue(self.book.balance_sheet()["identity_holds"])

    def test_no_escrow_account_everything_resolves(self):
        self.assertNotIn("1010", COA)                  # escrow is protocol, not book
        acc = self.book.trial_balance()["accounts"]
        self.assertEqual(acc["2030"], 0)               # deferred fully resolved
        self.assertEqual(acc["1020"], 0)               # every invoice collected
        self.assertEqual(acc["2000"], 0)               # payroll+workers paid
        self.assertEqual(acc["2010"], 0)               # band fees paid

    def test_invoices_match_the_stream(self):
        opens = sum(1 for r in self.rows if r["event"] == "open")
        settles = sum(1 for r in self.rows if r["event"] == "settle")
        refunds = sum(1 for r in self.rows if r["event"] == "refund")
        self.assertEqual(len(self.res["invoices"]), opens)
        self.assertEqual(sum(1 for i in self.res["invoices"].values()
                             if i["status"] == "earned"), settles)
        self.assertEqual(sum(1 for i in self.res["invoices"].values()
                             if i["status"] == "refunded"), refunds)

    def test_revenue_is_earned_not_promised(self):
        earned_total = sum(i["total_muc"] for i in self.res["invoices"].values()
                           if i["status"] == "earned")
        bs = self.book.balance_sheet()
        self.assertEqual(bs["revenue"], earned_total)
        self.assertGreater(bs["net_income"], 0)

    def test_payroll_booked_as_a_stream(self):
        n_workers = len(self.res["payroll"])
        self.assertGreater(n_workers, 0)
        self.assertEqual(sum(self.res["accrued_muc"].values()),
                         n_workers * 10 * usds(10))
        # the batch pays every worker obligation: settle payouts + salaries
        settle_payouts = sum(r["payout_muc"] for r in self.rows
                             if r["event"] == "settle")
        self.assertEqual(self.res["worker_paid_muc"],
                         settle_payouts + sum(self.res["accrued_muc"].values()))
        self.assertEqual(self.book.payable("2000"), 0)

    def test_anchors_land_in_the_ledger(self):
        led = WorkLedger()
        for r in self.rows:
            body = {k: v for k, v in r.items()
                    if k not in ("day", "event", "job", "agent")}
            led.append(day=r["day"], kind=r["event"], job_id=r.get("job", "-"),
                       agent=r.get("agent", "-"), **body)
        res = book_from_market_stream(self.rows, days=10, led=led)
        anchors = [e for e in led.entries if e["kind"] == "anchor"]
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors[0]["body"]["digest"],
                         res["book"].journal_digest())
        self.assertTrue(led.verify_chain()["ok"])

    def test_report_names_the_identity(self):
        self.assertIn("identity (A == L + E + NI): True", report(self.res))


if __name__ == "__main__":
    unittest.main()
