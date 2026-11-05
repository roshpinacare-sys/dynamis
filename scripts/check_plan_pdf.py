#!/usr/bin/env python3
"""check_plan_pdf.py — the founding plan PDF must never name the legacy chains.

The representation scrub (b71211d) covered md/py/html/yaml/json sources; the
rendered plan PDF was missed — 69 mentions were found and fixed on 2026-11-05
in the same commit as this checker. PDF text lives in subset-font glyph runs
(a naive byte/zlib scan sees none of it), so decoding uses poppler's
pdftotext. If pdftotext is unavailable the check reports SKIP and exits 0;
the local battery and CI (poppler-utils ships on GitHub ubuntu runners) are
the enforcement points.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "founding-plan.pdf"
FORBIDDEN = re.compile(r"\b(steem|hive|blurt|leofinance)\b", re.IGNORECASE)


def main() -> int:
    if not PDF.exists():
        print("check_plan_pdf: SKIP (no docs/founding-plan.pdf in repo)")
        return 0
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        print("check_plan_pdf: SKIP (pdftotext not installed here; "
              "CI and the local battery enforce this)")
        return 0
    out = subprocess.run([pdftotext, str(PDF), "-"],
                         capture_output=True, text=True, check=True)
    hits = FORBIDDEN.findall(out.stdout)
    print(f"check_plan_pdf: {len(hits)} findings in {PDF.name} "
          f"({len(out.stdout.splitlines())} text lines)")
    for h in hits[:10]:
        print(f"  FINDING: {h}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
