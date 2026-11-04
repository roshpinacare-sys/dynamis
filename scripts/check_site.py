#!/usr/bin/env python3
"""check_site.py — film and fix, for the static site.

The Stageshow method (benji.org/stageshow) says: build the demo, then *film it* and
fix what the film finds — film.mjs lays frames on a contact sheet, jumps.mjs catches
one-frame snaps, layout.mjs checks that text fits its boxes. A static site can be
filmed with what stdlib gives us, so this script measures what is measurable:

  1. anchors        every internal href="#x" resolves to an existing id="x";
  2. self-contained no external <script src> / <link href> (the site must run offline);
  3. the loop demo  the #loop section is present with its four evidence checks,
                    cursor, reduced-motion fallback and aria label;
  4. recentering    no legacy chain names anywhere in the public copy — DYNAMIS is
                    promoted as its own independent network; rails are adapters;
  5. counted truth  the test-count strip in the hero equals the number of tests the
                    suite actually collects (measured here, not remembered).

Exit 0 and a report, or exit 1 with the findings. Wired into CI after the test suite.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "index.html"

FORBIDDEN = ("steem", "hive", "blurt")     # legacy chains stay in the architecture,
                                           # never in the promotion
REQUIRED_DEMO = (
    'id="loop"', "artifact_runs", "contract_shape",
    "totals_match_ground_truth", "bounded_runtime",
    "stg-cursor", "prefers-reduced-motion",
    'aria-label="Animated demo: one job running through the DYNAMIS work loop',
)


def collect_tests() -> int:
    sys.path.insert(0, str(ROOT / "impl"))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "impl" / "tests"))
    return suite.countTestCases()


def check() -> list[str]:
    fails: list[str] = []
    html = SITE.read_text(encoding="utf-8")
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S)

    # 1. anchors resolve
    ids = set(re.findall(r'id="([^"]+)"', html))
    for href in set(re.findall(r'href="#([^"]+)"', html)):
        if href not in ids:
            fails.append(f"anchor #{href} has no matching id")

    # 2. self-contained
    for m in re.findall(r'<script[^>]+src="([^"]+)"', html) + \
             re.findall(r'<link[^>]+href="([^"]+)"', html):
        if m.startswith(("http://", "https://", "//")):
            fails.append(f"external resource: {m}")

    # 3. the loop demo
    for needle in REQUIRED_DEMO:
        if needle not in html:
            fails.append(f"loop demo missing: {needle}")

    # 4. recentering — no legacy chain names in the promotion
    for name in FORBIDDEN:
        if re.search(name, text, re.IGNORECASE):
            fails.append(f"legacy chain name in public copy: {name}")

    # 5. counted truth — the strip's number vs the suite's real count
    real = collect_tests()
    m = re.search(r"<b>(\d+)</b><span>tests green", html)
    if not m:
        fails.append("test-count strip not found in hero")
    elif int(m.group(1)) != real:
        fails.append(f"hero claims {m.group(1)} tests but the suite collects {real}")
    return fails, real


def main() -> int:
    fails, real = check()
    print(f"check_site: {len(fails)} findings · suite collects {real} tests")
    for f in fails:
        print(f"  FINDING: {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
