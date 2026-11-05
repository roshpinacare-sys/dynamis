#!/usr/bin/env python3
"""gate_review.py — the Day 7 gate review, generated from the registry.

specs/gates.yaml is the machine-readable law of progress: 23 packages across
four phases, each with an owner and a measurable acceptance criterion. This
script renders the registry as the gate-review document (docs/18, Day 7),
joining each package with the evidence actually on record in
specs/acceptance/EVIDENCE.md — so the review states what is measured, not
what is hoped.

Status semantics (honest, two-valued — the acceptance text carries the rest):
  * owner "A"    → the package's executable half is in the codebase; the
                   acceptance criterion still needs its live measurement.
  * owner has O  → everything code can do is done; the remaining act is
                   the owner's (docs/18 day plan).

  python3 scripts/gate_review.py --evidence > records/gate-review-2026-11-12.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATES = ROOT / "specs" / "gates.yaml"
EVIDENCE = ROOT / "specs" / "acceptance" / "EVIDENCE.md"

PKG_RE = re.compile(
    r"\{id:\s*\"?(?P<id>[0-9.]+)\"?,\s*owner:\s*\"?(?P<owner>[^,}]+?)\"?,\s*"
    r"title:\s*(?P<title>.+?),\s*acceptance:\s*\"(?P<acceptance>[^\"]*)\"\s*\}")


def _parse_packages(gates_path: Path = GATES) -> list[dict]:
    text = gates_path.read_text(encoding="utf-8")
    pkgs: list[dict] = []
    for m in PKG_RE.finditer(text):
        pkgs.append({"id": m.group("id"), "owner": m.group("owner").strip(),
                     "title": m.group("title").strip(),
                     "acceptance": m.group("acceptance").strip(),
                     "phase": _phase_of(text, m.start())})
    return pkgs


def _phase_of(text: str, pos: int) -> dict:
    """The phase block containing byte offset pos (id, name, weeks)."""
    best: dict = {"id": "?", "name": "?", "weeks": "?"}
    for m in re.finditer(
            r"id:\s*phase-(\d+)\s*\n\s*name:\s*(\S+)\s*\n\s*weeks:\s*\[(\d+),\s*(\d+)\]",
            text):
        if m.start() < pos:
            best = {"id": int(m.group(1)), "name": m.group(2),
                    "weeks": f"{m.group(3)}–{m.group(4)}"}
    return best


def _evidence_counts(evidence_path: Path = EVIDENCE) -> dict[str, list[str]]:
    """gate id -> evidence lines whose subject field names that gate."""
    counts: dict[str, list[str]] = {}
    if not evidence_path.exists():
        return counts
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        fields = [f.strip() for f in line.split("|")]
        if len(fields) < 3 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields[0]):
            continue
        first = fields[1].split()[0] if fields[1].split() else ""
        if re.fullmatch(r"[0-3]\.[0-9]", first):
            counts.setdefault(first, []).append(line)
    return counts


def review(gates_path: Path = GATES, evidence_path: Path = EVIDENCE,
           *, with_evidence: bool = False) -> str:
    pkgs = _parse_packages(gates_path)
    ev = _evidence_counts(evidence_path)
    out = ["# Gate review — generated from specs/gates.yaml", "",
           "Status semantics: **owner A** = executable half in code, live "
           "acceptance still needs its measurement; **owner O** = the "
           "remaining act is the owner's (docs/18). Evidence counts join "
           "specs/acceptance/EVIDENCE.md.", ""]
    phases: dict[int, list[dict]] = {}
    for p in pkgs:
        phases.setdefault(p["phase"]["id"], []).append(p)
    for pid in sorted(phases):
        meta = phases[pid][0]["phase"]
        out.append(f"## Phase {pid} — {meta['name']} (weeks {meta['weeks']})")
        out.append("")
        out.append("| Gate | Owner | Title | Acceptance | Evidence |")
        out.append("|---|---|---|---|---|")
        for p in sorted(phases[pid], key=lambda x: x["id"]):
            n = len(ev.get(p["id"], []))
            out.append(f"| {p['id']} | {p['owner']} | {p['title']} | "
                       f"{p['acceptance']} | {n} |")
        out.append("")
        if with_evidence:
            for p in sorted(phases[pid], key=lambda x: x["id"]):
                for line in ev.get(p["id"], []):
                    out.append(f"- gate {p['id']}: {line}")
            if any(ev.get(p["id"]) for p in phases[pid]):
                out.append("")
    owner_pending = [p for p in pkgs if "O" in p["owner"]]
    out.append(f"## Summary — {len(pkgs)} packages, {len(owner_pending)} "
               f"with an owner act pending")
    out.append("")
    out.append("Owner acts: " + ", ".join(f"`{p['id']}`" for p in owner_pending)
               + ". Everything else is code-complete pending its live "
               "measurement; the calendar windows accrue via the scheduled "
               "workflows (docs/18-launch-week.md).")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the gate review, from the registry")
    ap.add_argument("--evidence", action="store_true",
                    help="list the matched evidence lines under each phase")
    ns = ap.parse_args(argv)
    print(review(with_evidence=ns.evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
