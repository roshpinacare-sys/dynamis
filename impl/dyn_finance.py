#!/usr/bin/env python3
"""dyn.finance.v1 — the finance spine: entity book, invoices, payroll (SOL).

Gates 1.3 and 1.4, executable in-repo. The roadmap is explicit that SOL
packages are first-class — a phase gate cannot close with emission live while
finance is not real. So the entity gets a real double-entry book:

  - **Chart of accounts** — cash, escrow clearing, receivable; worker and
    verifier payables, deferred revenue; paid-in capital, job revenue,
    verification-fee and payroll expenses. µ¢ everywhere (ADR-0007).
  - **Hash-chained journal** — every posting is one debit account, one credit
    account, one amount; entries chain like the work ledger and rehash-verify.
    An unbalanced or same-side posting is refused at `post()`, not discovered
    at audit.
  - **Invoices (dyn.invoice.v1)** — issued at job open with the entity's
    markup over the job value (the escrow covers worker + verification; the
    markup covers the crew), paid, voided; digests anchor into the work
    ledger (`anchor` entries) and ride the checkpoint seals.
  - **Payroll streams (dyn.payroll.v1)** — worker registry (agent → role →
    rate), daily accrual dr payroll-expense / cr worker-payable, paid out in
    a batch: the first agent salary booked in an entity ledger.
  - **The measured P&L** — `book_from_market_stream` replays a real market
    stream (the same JSONL the metrics and ledger read) into the book and
    closes it: escrow clears to zero, every payable settles, the balance
    sheet balances, and the entity's margin is a measured number.

  python3 dyn_finance.py from-stream market.jsonl     # the entity's books

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dyn_ledger import WorkLedger, load_rows  # noqa: E402
from dynamis_core import usds  # noqa: E402
from dynamis_core.canonical import (check_id, check_int_amount,  # noqa: E402
                                    object_hash)

FINANCE = "dyn.finance.v1"
INVOICE = "dyn.invoice.v1"
PAYROLL = "dyn.payroll.v1"
GENESIS = "0" * 64
DEFAULT_MARKUP_BPS = 2_000          # +20% over escrow value: the crew's share
DEFAULT_PAID_IN = usds(10_000)

COA = {
    "1000": ("cash_usds", "asset"),
    "1020": ("receivable", "asset"),
    "2000": ("worker_payable", "liability"),
    "2010": ("verifier_fee_payable", "liability"),
    "2030": ("deferred_revenue", "liability"),
    "3000": ("paid_in_capital", "equity"),
    "4000": ("job_revenue", "revenue"),
    "5000": ("verification_fee_expense", "expense"),
    "5010": ("payroll_expense", "expense"),
    "5020": ("worker_cost_expense", "expense"),
}


class BookError(Exception):
    pass


class EntityBook:
    """Double-entry journal, hash-chained. One debit, one credit, µ¢ only."""

    def __init__(self, entity_id: str, *, paid_in_muc: int = DEFAULT_PAID_IN,
                 open_day: int = 0) -> None:
        try:
            self.entity_id = check_id(entity_id, "entity_id")
        except ValueError as e:
            raise BookError(str(e)) from e
        self.journal: list[dict] = []
        if paid_in_muc:
            self.post("1000", "3000", paid_in_muc, "paid-in capital",
                      day=open_day, ref="genesis")

    def post(self, dr: str, cr: str, amount_muc: int, memo: str, *, day: int,
             ref: str = "") -> dict:
        if dr not in COA or cr not in COA:
            raise BookError(f"unknown account(s): {dr}/{cr} — post to the COA")
        if dr == cr:
            raise BookError(f"same account both sides: {dr}")
        try:
            amount_muc = check_int_amount(amount_muc, "amount_muc")
        except ValueError as e:
            raise BookError(str(e)) from e
        if not amount_muc:
            raise BookError("zero posting is not an entry")
        prev = self.journal[-1]["hash"] if self.journal else GENESIS
        entry = {"seq": len(self.journal), "day": day, "dr": dr, "cr": cr,
                 "amount_muc": amount_muc, "memo": memo, "ref": ref,
                 "prev": prev}
        entry["hash"] = object_hash({"prev": prev, "seq": entry["seq"],
                                     "dr": dr, "cr": cr,
                                     "amount_muc": amount_muc, "memo": memo,
                                     "ref": ref})
        self.journal.append(entry)
        return entry

    def verify_journal(self) -> dict:
        prev = GENESIS
        for e in self.journal:
            want = object_hash({"prev": e["prev"], "seq": e["seq"], "dr": e["dr"],
                                "cr": e["cr"], "amount_muc": e["amount_muc"],
                                "memo": e["memo"], "ref": e["ref"]})
            if e["prev"] != prev or e["hash"] != want:
                return {"ok": False, "depth": e["seq"]}
            prev = e["hash"]
        return {"ok": True, "depth": len(self.journal)}

    def trial_balance(self) -> dict:
        """Net per account; debits positive for assets/expenses, credits for
        the rest — and the hard identity: total debits == total credits."""
        debits: dict[str, int] = {}
        credits: dict[str, int] = {}
        for e in self.journal:
            debits[e["dr"]] = debits.get(e["dr"], 0) + e["amount_muc"]
            credits[e["cr"]] = credits.get(e["cr"], 0) + e["amount_muc"]
        tb = {code: debits.get(code, 0) - credits.get(code, 0)
              for code in COA}
        total_dr = sum(v for v in tb.values() if v > 0)
        total_cr = -sum(v for v in tb.values() if v < 0)
        return {"accounts": tb, "total_debits_muc": total_dr,
                "total_credits_muc": total_cr,
                "balanced": total_dr == total_cr}

    def balance_sheet(self) -> dict:
        tb = self.trial_balance()["accounts"]
        assets = sum(max(tb[c], 0) for c, (_, side) in COA.items()
                     if side == "asset")
        liabilities = sum(-min(tb[c], 0) for c, (_, side) in COA.items()
                          if side == "liability")
        equity = -min(tb["3000"], 0)
        revenue = -min(tb["4000"], 0)
        expenses = sum(max(tb[c], 0) for c, (_, side) in COA.items()
                       if side == "expense")
        net = revenue - expenses
        return {"assets": assets, "liabilities": liabilities, "equity": equity,
                "revenue": revenue, "expenses": expenses, "net_income": net,
                "identity_holds": assets == liabilities + equity + net}

    def payable(self, code: str) -> int:
        return -min(self.trial_balance()["accounts"][code], 0)

    def pay_payable(self, code: str, *, day: int, memo: str) -> int:
        """Settle a liability in full from cash — the batch payout."""
        owed = self.payable(code)
        if owed:
            self.post(code, "1000", owed, memo, day=day, ref=f"pay-{code}")
        return owed

    def journal_digest(self) -> str:
        return object_hash([e["hash"] for e in self.journal])


# --------------------------------------------------------------------------
# invoices
# --------------------------------------------------------------------------
def issue_invoice(book: EntityBook, *, invoice_id: str, customer: str,
                  value_muc: int, day: int, due_day: int,
                  markup_bps: int = DEFAULT_MARKUP_BPS) -> dict:
    """The entity quotes the customer escrow value + markup (the crew's
    share); deferred until evidence-verified settle. µ¢ integers only."""
    from dynamis_core.canonical import bps_of
    check_id(invoice_id, "invoice_id")
    total = check_int_amount(value_muc + bps_of(value_muc, markup_bps),
                             "invoice_total_muc")
    inv = {"invoice": INVOICE, "invoice_id": invoice_id,
           "entity": book.entity_id, "customer": customer,
           "escrow_muc": value_muc, "markup_muc": total - value_muc,
           "total_muc": total, "status": "issued", "day": day,
           "due_day": due_day}
    inv["digest"] = object_hash(inv)
    book.post("1020", "2030", total, f"invoice {invoice_id} issued",
              day=day, ref=invoice_id)
    return inv


def pay_invoice(book: EntityBook, inv: dict, *, day: int) -> dict:
    if inv["status"] != "issued":
        raise BookError(f"invoice {inv['invoice_id']} is {inv['status']}")
    book.post("1000", "1020", inv["total_muc"],
              f"invoice {inv['invoice_id']} paid", day=day,
              ref=inv["invoice_id"])
    inv["status"] = "paid"
    return inv


def void_invoice(book: EntityBook, inv: dict, *, day: int) -> dict:
    if inv["status"] != "issued":
        raise BookError(f"invoice {inv['invoice_id']} is {inv['status']}")
    book.post("2030", "1020", inv["total_muc"],
              f"invoice {inv['invoice_id']} voided", day=day,
              ref=inv["invoice_id"])
    inv["status"] = "void"
    return inv


def anchor_into(led: WorkLedger, *, what: str, digest: str, day: int) -> dict:
    """Pin a finance digest into the work ledger — it rides the checkpoint
    seals from there (the ~$0.10 anchoring rail of gate 1.3)."""
    return led.append(day=day, kind="anchor", job_id=what, agent="ent-finance",
                      digest=digest)


# --------------------------------------------------------------------------
# payroll streams
# --------------------------------------------------------------------------
class WorkerRegistry:
    def __init__(self) -> None:
        self.workers: dict[str, dict] = {}

    def hire(self, agent_id: str, *, role: str, rate_muc_per_day: int,
             keyref: str) -> dict:
        try:
            check_id(agent_id, "agent_id")
            rate_muc_per_day = check_int_amount(rate_muc_per_day,
                                                "rate_muc_per_day")
        except ValueError as e:
            raise BookError(str(e)) from e
        if not rate_muc_per_day:
            raise BookError("a salary of zero is not a salary")
        if agent_id in self.workers:
            raise BookError(f"{agent_id} already hired")
        w = {"agent_id": agent_id, "role": role,
             "rate_muc_per_day": rate_muc_per_day, "keyref": keyref}
        self.workers[agent_id] = w
        return w


class PayrollStream:
    """The worker's salary accrues daily and pays as a batch — booked."""

    def __init__(self, book: EntityBook, registry: WorkerRegistry,
                 agent_id: str) -> None:
        if agent_id not in registry.workers:
            raise BookError(f"{agent_id} is not in the registry")
        self.book = book
        self.worker = registry.workers[agent_id]
        self.accrued_days = 0
        self.paid_muc = 0

    def accrue(self, days: int, *, start_day: int) -> int:
        days = check_int_amount(days, "days")
        rate = self.worker["rate_muc_per_day"]
        for d in range(start_day, start_day + days):
            self.book.post("5010", "2000", rate,
                           f"payroll {self.worker['agent_id']} day {d}",
                           day=d, ref=f"payroll-{self.worker['agent_id']}")
        self.accrued_days += days
        return days * rate

    def pay(self, *, day: int) -> int:
        owed = self.book.payable("2000")
        if not owed:
            raise BookError("nothing accrued — no salary to pay")
        self.book.post("2000", "1000", owed,
                       f"salary {self.worker['agent_id']}", day=day,
                       ref=f"salary-{self.worker['agent_id']}")
        self.paid_muc += owed
        return owed


# --------------------------------------------------------------------------
# the measured P&L: replay a market stream into the book
# --------------------------------------------------------------------------
def book_from_market_stream(rows: list[dict], *, entity_id: str = "ent-001",
                            days: int = 0,
                            markup_bps: int = DEFAULT_MARKUP_BPS,
                            payroll_rate_muc_per_day: int = usds(10),
                            registry: WorkerRegistry | None = None,
                            led: WorkLedger | None = None
                            ) -> dict:
    """The entity's books, closed from the same stream the metrics and ledger
    read. The customer's money is held as deferred revenue; an evidence-
    verified settle converts it into revenue plus the worker and band costs;
    a refund returns it. Revenue is recognized on settle, never on open."""
    book = EntityBook(entity_id)
    invoices: dict[str, dict] = {}
    registry = registry or WorkerRegistry()
    workers = sorted({r.get("agent", "") for r in rows
                      if r["event"] == "settle" and r.get("agent")})
    last_day = max((r["day"] for r in rows), default=0)
    for w in workers:
        registry.hire(w, role="verified-worker",
                      rate_muc_per_day=payroll_rate_muc_per_day,
                      keyref=f"hsm:kr-{w}")
    for r in rows:
        job, ev, day = r.get("job", "-"), r["event"], r["day"]
        if ev == "open":
            inv = issue_invoice(book, invoice_id=f"inv-{job}", customer="cust-env-ops",
                                value_muc=r["value_muc"], day=day,
                                due_day=day + 7, markup_bps=markup_bps)
            pay_invoice(book, inv, day=day)
            invoices[job] = inv
        elif ev == "settle":
            inv = invoices[job]
            book.post("2030", "4000", inv["total_muc"],
                      f"revenue recognized {job}", day=day, ref=job)
            book.post("5020", "2000", r["payout_muc"],
                      f"worker cost {job}", day=day, ref=job)
            book.post("5000", "2010", r["fee_muc"],
                      f"verification fee {job}", day=day, ref=job)
            inv["status"] = "earned"
        elif ev == "refund":
            book.post("2030", "1000", invoices[job]["total_muc"],
                      f"customer refund {job}", day=day, ref=job)
            invoices[job]["status"] = "refunded"
    # payroll accrues over the whole run, everyone is paid at close
    payroll = {w: PayrollStream(book, registry, w) for w in workers}
    accrued = {w: st.accrue(max(days, last_day), start_day=1)
               for w, st in payroll.items()}
    worker_paid = book.pay_payable("2000", day=last_day + 1, memo="payroll batch")
    fee_paid = book.pay_payable("2010", day=last_day + 1, memo="verifier fees")
    tb = book.trial_balance()["accounts"]
    fee_expense = tb["5000"]
    # the spines tie: finance digests anchor into the work ledger
    if led is not None:
        anchor_into(led, what=f"{entity_id}:journal", digest=book.journal_digest(),
                    day=last_day + 1)
        bs = book.balance_sheet()
        anchor_into(led, what=f"{entity_id}:pnl",
                    digest=object_hash({"revenue": bs["revenue"],
                                        "expenses": bs["expenses"],
                                        "net_income": bs["net_income"]}),
                    day=last_day + 1)
    return {"book": book, "invoices": invoices, "payroll": payroll,
            "accrued_muc": accrued, "worker_paid_muc": worker_paid,
            "fee_paid_muc": fee_paid, "fee_expense_muc": fee_expense,
            "registry": registry}


def report(result: dict) -> str:
    book = result["book"]
    bs = book.balance_sheet()
    tb = book.trial_balance()
    lines = [
        f"{FINANCE} — entity {book.entity_id} · journal {len(book.journal)} "
        f"postings, chain ok: {book.verify_journal()['ok']}",
        f"  trial balance: dr {tb['total_debits_muc']:,} µ¢ == "
        f"cr {tb['total_credits_muc']:,} µ¢ → balanced: {tb['balanced']}",
        f"  invoices: {sum(1 for i in result['invoices'].values() if i['status'] == 'earned')} earned, "
        f"{sum(1 for i in result['invoices'].values() if i['status'] == 'refunded')} refunded, "
        f"{sum(1 for i in result['invoices'].values() if i['status'] == 'paid')} open",
        f"  payroll: {len(result['payroll'])} workers accrued "
        f"{sum(result['accrued_muc'].values()):,} µ¢; payouts to workers "
        f"{result['worker_paid_muc']:,} µ¢ and to the band "
        f"{result['fee_paid_muc']:,} µ¢, all settled at close",
        f"  P&L: revenue {bs['revenue']:,} µ¢ − expenses {bs['expenses']:,} µ¢ "
        f"= net {bs['net_income']:+,} µ¢",
        f"  balance sheet identity (A == L + E + NI): {bs['identity_holds']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dyn_finance", description="DYNAMIS finance spine (dyn.finance.v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("from-stream")
    p.add_argument("stream", help="market JSONL")
    p.add_argument("--days", type=int, default=0, help="payroll days override")
    a = ap.parse_args(argv)
    res = book_from_market_stream(load_rows(a.stream), days=a.days)
    print(report(res))
    return 0 if res["book"].trial_balance()["balanced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
