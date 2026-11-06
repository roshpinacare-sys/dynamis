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

from dyn_bridge import (CARD_VERSION, SURFACES_BUNDLE, BridgeError,  # noqa: E402
                        export_cards)
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


def validate_surfaces(bundle_dir: Path) -> list[str]:
    """Offline validation of the full discovery bundle (docs/18 Day 6).

    Every artifact digest recomputes from the file bytes' parsed object; the
    bundle root recomputes over the sorted (path, digest) pairs; and the
    package cross-checks against the cards — a skill's holders must be real
    card digests whose capabilities include the skill's declared capability,
    and the A2A card's skills must be exactly the packaged ones.
    """
    fails: list[str] = []
    mpath = bundle_dir / "manifest.json"
    if not mpath.exists():
        return [f"manifest.json missing in {bundle_dir}"]
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("bundle") != SURFACES_BUNDLE:
        fails.append(f"unknown bundle kind: {manifest.get('bundle')!r} "
                     f"!= {SURFACES_BUNDLE!r}")
    arts = manifest.get("artifacts", {})
    for path, stated in sorted(arts.items()):
        f = bundle_dir / path
        if not f.exists():
            fails.append(f"artifact missing: {path}")
            continue
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            fails.append(f"artifact {path}: not parseable JSON: {e}")
            continue
        digest = object_hash(obj)[:32]
        if digest != stated:
            fails.append(f"artifact {path}: digest mismatch — edited after export")
    root = object_hash({"artifacts": [[k, arts[k]] for k in sorted(arts)]})[:32]
    if manifest.get("root") != root:
        fails.append(f"bundle root mismatch: stated {manifest.get('root')} "
                     f"!= recomputed {root} — the bundle was edited after export")

    def artifact(path: str) -> dict:
        return json.loads((bundle_dir / path).read_text(encoding="utf-8"))

    if {"erc8004-cards.json", "a2a-agent-card.json", "skills.json"} - set(arts):
        fails.append("bundle is missing a core artifact (cards / a2a / skills)")
        return fails
    cards = artifact("erc8004-cards.json")["cards"]
    fails.extend(validate(artifact("erc8004-cards.json")))
    by_id = {c["identity"]["agent_id"]: c for c in cards}
    a2a = artifact("a2a-agent-card.json")
    sk = artifact("skills.json")
    if {s["id"] for s in a2a.get("skills", [])} != {s["id"] for s in sk.get("skills", [])}:
        fails.append("A2A card skills != skills.json skills — the surfaces disagree")
    for s in sk.get("skills", []):
        if s.get("wire_schema") not in arts:
            fails.append(f"skill {s.get('id')}: wire schema "
                         f"{s.get('wire_schema')!r} is not in the bundle")
        digest_by_id = {c["identity"]["agent_id"]: c["card_digest"] for c in cards}
        for h in s.get("holders", []):
            if h not in by_id:
                fails.append(f"skill {s.get('id')}: holder {h} is not in the "
                             f"export set")
                continue
            held = by_id[h]["capabilities"]
            if not any(cap in held for cap in s.get("capability", [])):
                fails.append(f"skill {s.get('id')}: holder {h} holds none of "
                             f"{s.get('capability')} — the package would lie")
        for dg in s.get("holder_card_digests", []):
            ids = [i for i, d in digest_by_id.items() if d == dg]
            if not ids:
                fails.append(f"skill {s.get('id')}: holder digest {dg} not in "
                             f"the export set")
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
    ap.add_argument("--surfaces", metavar="DIR", default=None,
                    help="validate a discovery bundle directory instead")
    ns = ap.parse_args(argv)
    if ns.surfaces:
        fails = validate_surfaces(Path(ns.surfaces))
        n = len(json.loads((Path(ns.surfaces) / "manifest.json")
                           .read_text(encoding="utf-8")).get("artifacts", {}))
        if not fails:
            print(f"surfaces: OK — {n} artifact(s) in {ns.surfaces}; every "
                  f"digest and the bundle root recompute offline, skills "
                  f"cross-check against the cards")
        for f in fails:
            print(f"  FINDING: {f}")
        print(f"check_cards: {len(fails)} findings")
        return 1 if fails else 0
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
