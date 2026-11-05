#!/usr/bin/env python3
"""params_check.py — the code and the ratified params must never diverge.

params/genesis.yaml is the single source of every canonical number (gate 0.4:
the owner ratifies it). The implementation mirrors those values as named
constants — but a mirror that is never checked is a wish. This script proves
the mirror holds, leaf by leaf, and exits non-zero on any divergence. CI runs
it, so nobody can change a rate in code without changing the ratified params,
or vice versa.

Parsing is deliberately narrow (stdlib only, ADR-0007): each mirrored leaf is
located by its section path and compared exactly — no general YAML parser, no
best-effort fallback. A missing leaf or an unreadable value is a finding;
fail closed.

  python3 scripts/params_check.py             # the whole mirror, CI-grade
  python3 scripts/params_check.py --status    # also report gate 0.4 state
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))

from dyn_bench import CHALLENGE_SEEDS, TIERS, WORK_BUDGET_STEPS  # noqa: E402
from dyn_post import (DEFAULT_EMBED_HEIGHT, MAX_EMBED_HEIGHT,  # noqa: E402
                      MAX_LIVE_EMBEDS, MAX_LIVE_EMBED_BYTES, MAX_POST_BYTES)
from dynamis_core.canonical import MU_PER_USDS  # noqa: E402
from dynamis_core.emission import DYN_MU_PER_USDS_MUC  # noqa: E402
from dynamis_core.escrow import COORDINATION_FEE_BPS  # noqa: E402
from dynamis_core.policy import (MIN_RUNWAY_MONTHS, RAIL_MAX_DAILY_MUC,  # noqa: E402
                                 RAIL_MAX_SINGLE_MUC, T2_THRESHOLD_MUC)

GENESIS = ROOT / "params" / "genesis.yaml"


def _sections(text: str) -> dict[tuple[str, ...], tuple[int, int]]:
    """Map section path -> (start_line, end_line), exclusive end.

    A section starts at its `key:` line (even indent: 0, 2, 4) and ends at the
    next mapping line whose indent is <= its own. Depth 3 is all the file uses.
    """
    lines = text.splitlines()
    marks: list[tuple[int, str, int]] = []     # (indent, key, line_no)
    for i, ln in enumerate(lines):
        code = ln.split("#", 1)[0].rstrip()
        stripped = code.strip()
        if not stripped or stripped.startswith("- ") or ":" not in code:
            continue
        key = stripped.split(":", 1)[0].strip()
        if not key or re.search(r"\s", key):
            continue
        marks.append((len(code) - len(code.lstrip(" ")), key, i))
    out: dict[tuple[str, ...], tuple[int, int]] = {}
    for level in (0, 2, 4):
        for idx, (indent, key, start) in enumerate(marks):
            if indent != level:
                continue
            end = len(lines)
            for ind2, _k2, s2 in marks:
                if s2 > start and ind2 <= level:
                    end = min(end, s2)
            parent = tuple(k for ind, k, s in marks
                           if s < start and ind < level and ind == level - 2
                           ) if level else ()
            if level:
                parents = [(s, k) for ind, k, s in marks
                           if ind == level - 2 and s < start]
                if not parents:
                    continue
                parent = (parents[-1][1],)
            out[parent + (key,) if level else (key,)] = (start, end)
    return out


def _leaf(text: str, path: tuple[str, ...]) -> str:
    """The raw scalar value at path (last element = the leaf key), else raise."""
    lines = text.splitlines()
    secs = _sections(text)
    start, end = secs[path[:-1]] if len(path) > 1 else (0, len(lines))
    pat = re.compile(r"^\s*" + re.escape(path[-1]) + r"\s*:\s*(.+?)\s*(?:#.*)?$")
    for ln in lines[start:end]:
        m = pat.match(ln)
        if m:
            return m.group(1).strip().strip('"')
    raise KeyError(".".join(path))


def _int(raw: str) -> int:
    return int(raw.replace("_", "").strip(), 0)


def check(genesis_path: Path = GENESIS) -> list[str]:
    """Return one finding per divergence/missing leaf; [] means the mirror holds."""
    text = genesis_path.read_text(encoding="utf-8")
    fails: list[str] = []

    def eq(path: tuple[str, ...], expected: int, name: str) -> None:
        try:
            got = _int(_leaf(text, path))
        except KeyError:
            fails.append(f"missing leaf: {'.'.join(path)} (mirrors {name})")
            return
        if got != expected:
            fails.append(f"DIVERGENCE {'.'.join(path)}: params {got} "
                         f"!= code {expected} ({name})")

    eq(("supply", "dyn_mu_per_usds_muc"), DYN_MU_PER_USDS_MUC,
       "emission.DYN_MU_PER_USDS_MUC")
    eq(("supply", "dyn_initial_mint"), 0, "anti-premine law")
    eq(("escrow", "coordination_fee_bps"), COORDINATION_FEE_BPS,
       "escrow.COORDINATION_FEE_BPS")
    eq(("posts", "max_post_bytes"), MAX_POST_BYTES, "dyn_post.MAX_POST_BYTES")
    eq(("posts", "max_live_embed_bytes"), MAX_LIVE_EMBED_BYTES,
       "dyn_post.MAX_LIVE_EMBED_BYTES")
    eq(("posts", "max_live_embeds"), MAX_LIVE_EMBEDS, "dyn_post.MAX_LIVE_EMBEDS")
    eq(("posts", "max_embed_height"), MAX_EMBED_HEIGHT, "dyn_post.MAX_EMBED_HEIGHT")
    eq(("posts", "default_embed_height"), DEFAULT_EMBED_HEIGHT,
       "dyn_post.DEFAULT_EMBED_HEIGHT")
    for tier, threshold in TIERS:
        eq(("bench", "tier_thresholds_muc", tier), threshold,
           f"bench.TIERS[{tier}]")
    eq(("bench", "work_budget_steps"), WORK_BUDGET_STEPS,
       "bench.WORK_BUDGET_STEPS")
    try:
        got = [_int(p) for p in _leaf(text, ("bench", "challenge_seeds"))
               .strip("[]").split(",")]
        if got != list(CHALLENGE_SEEDS):
            fails.append(f"DIVERGENCE bench.challenge_seeds: params {got} "
                         f"!= code {list(CHALLENGE_SEEDS)}")
    except KeyError:
        fails.append("missing leaf: bench.challenge_seeds "
                     "(mirrors bench.CHALLENGE_SEEDS)")
    eq(("treasury_policy", "t2_threshold_usds"), T2_THRESHOLD_MUC // MU_PER_USDS,
       "policy.T2_THRESHOLD_MUC")
    eq(("treasury_policy", "rail_caps", "max_single_flow_usds"),
       RAIL_MAX_SINGLE_MUC // MU_PER_USDS, "policy.RAIL_MAX_SINGLE_MUC")
    eq(("treasury_policy", "rail_caps", "max_daily_usds"),
       RAIL_MAX_DAILY_MUC // MU_PER_USDS, "policy.RAIL_MAX_DAILY_MUC")
    eq(("treasury_policy", "min_runway_months"), MIN_RUNWAY_MONTHS,
       "policy.MIN_RUNWAY_MONTHS")
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="genesis params ↔ code mirror")
    ap.add_argument("--quiet", action="store_true", help="only the verdict")
    ap.add_argument("--status", action="store_true",
                    help="also report ratification state (gate 0.4)")
    ns = ap.parse_args(argv)
    if ns.status:
        text = GENESIS.read_text(encoding="utf-8")
        m = re.search(r"^\s*status:\s*(\S+)", text, re.M)
        print(f"ratification: meta.status = {m.group(1) if m else '?'} "
              f"(gate 0.4 closes when the owner signs)")
        for adr in sorted((ROOT / "adr").glob("0*.md")):
            am = re.search(r"\*\*Status\*\*:\s*([^\n(]+)",
                           adr.read_text(encoding="utf-8"))
            if am:
                print(f"  {adr.stem}: {am.group(1).strip()}")
    fails = check()
    if not ns.quiet and not fails:
        print(f"params mirror: OK — {GENESIS.name} matches the code "
              f"constants, leaf by leaf")
    for f in fails:
        print(f"  FINDING: {f}")
    print(f"params_check: {len(fails)} divergences")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
