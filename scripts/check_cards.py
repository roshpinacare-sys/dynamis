#!/usr/bin/env python3
"""check_cards.py — offline validation of the ERC-8004 export set (docs/18
Day 6 prep).

The bridge (impl/dyn_bridge.py) exports discovery cards plus a manifest whose
root commits to the sorted card digests. The Day 6 acceptance is an *external*
instance discovering DYN from the export alone — so the export must be valid
without any runtime. This script is that check, runnable by anyone offline:

  * every card is well-formed (version, id pattern, digest recomputes);
  * the manifest root recomputes from the cards alone — nothing hidden;
  * the count agrees; duplicate or raw-key-carrying passports were already
    refused at export time (the bridge fails closed).

  python3 impl/dyn_bridge.py export /tmp/cards.json     # make an export
  python3 scripts/check_cards.py /tmp/cards.json        # validate it offline

With no argument, the validator exports the bridge's own sample set and
validates it — the CI-grade self-check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "impl"))

from dyn_bridge import CARD_VERSION, BridgeError, export_cards  # noqa: E402
from dynamis_core.canonical import object_hash  # noqa: E402

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{32}$")


def validate(export: dict) -> list[str]:
    """Return one finding per problem; [] means the export set is valid."""
    fails: list[str] = []
    cards = export.get("cards", [])
    manifest = export.get("manifest", {})
    if manifest.get("count") != len(cards):
        fails.append(f"manifest.count {manifest.get('count')} != "
                     f"{len(cards)} cards present")
    digests = sorted(c.get("card_digest") for c in cards)
    root = object_hash({"sorted_digests": digests,
                        "count": len(cards)})[:32]
    if manifest.get("root") != root:
        fails.append(f"manifest root mismatch: stated {manifest.get('root')} "
                     f"!= recomputed {root} — the set was edited after export")
    for c in cards:
        aid = c.get("identity", {}).get("agent_id", "")
        if not ID_RE.fullmatch(aid):
            fails.append(f"card id malformed: {aid!r} (needs {ID_RE.pattern})")
        if c.get("version") != CARD_VERSION:
            fails.append(f"card {aid}: version {c.get('version')!r} "
                         f"!= {CARD_VERSION!r}")
        stated = c.get("card_digest", "")
        if not DIGEST_RE.fullmatch(stated):
            fails.append(f"card {aid}: card_digest malformed: {stated!r}")
            continue
        recomputed = object_hash({k: v for k, v in c.items()
                                  if k != "card_digest"})[:32]
        if stated != recomputed:
            fails.append(f"card {aid}: card_digest does not recompute — "
                         f"the card was edited after export")
    return fails


def samples_export() -> dict:
    """The bridge's self-contained sample set, exported in-process."""
    from dynamis_core.objects import AgentPassport
    passports = [
        AgentPassport("agent-alpha", "alpha operator", ("hsm:k1",),
                      ("post.dyn.v1", "verify.classB"), "pw-alpha", 12),
        AgentPassport("agent-beta", "beta operator", ("hsm:k2",),
                      ("work.escrow", "verify.classC"), "pw-beta", 12),
    ]
    return export_cards(passports)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="offline ERC-8004 export check")
    ap.add_argument("path", nargs="?", default=None,
                    help="exported JSON file; omit to self-check the samples")
    ns = ap.parse_args(argv)
    if ns.path:
        export = json.loads(Path(ns.path).read_text(encoding="utf-8"))
        src = ns.path
    else:
        export = samples_export()
        src = "bridge sample set"
    fails = validate(export)
    n = export.get("manifest", {}).get("count", len(export.get("cards", [])))
    if not fails:
        print(f"cards: OK — {n} card(s) in {src}; manifest root and every "
              f"card digest recompute offline")
    for f in fails:
        print(f"  FINDING: {f}")
    print(f"check_cards: {len(fails)} findings")
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BridgeError as e:
        print(f"  FINDING: bridge refused the export: {e}")
        raise SystemExit(1)
