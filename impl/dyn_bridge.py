#!/usr/bin/env python3
"""dyn.bridge.v1 — the ERC-8004 export bridge (gate 3.5, executable).

External discovery without root dependency (docs/05 3.5): the bridge is an
*export-only* converter. It reads finished passport objects and emits
ERC-8004-shaped discovery cards as plain, canonical-hash-stamped JSON. It
never feeds the core loop — the runtime runs untouched with this module
absent, and the test suite proves that import isolation.

  - **Cards** — identity (agent id, persona, zero key material), capabilities
    (scoped list), reputation (receipts anchor digest + census day). Exactly
    the ERC-8004 fields external registries expect, nothing root-shaped (Law 17).
  - **Manifest** — the exported set carries a Merkle-style canonical root over
    the sorted card digests; an external party verifies the set offline by
    recomputing roots. No call home, no runtime dependency, ever.
  - **Zero-material rule** — passports already hold only HSM keyrefs; the card
    emits the fingerprint digest, never the ref itself, and refuses a passport
    that somehow carries raw material (defense in depth on Law 3).

Gate 3.5 acceptance: agents discoverable externally from the export alone;
import isolation measured in `tests/test_dyn_bridge.py`.

  python3 dyn_bridge.py export examples.json     # cards + manifest, printed
  python3 dyn_bridge.py surfaces site/discovery  # the full discovery bundle:
                                                 # cards, the job-rail A2A card,
                                                 # the skill package (holders
                                                 # derived from the cards, never
                                                 # hand-written), and the wire
                                                 # schemas — every artifact
                                                 # digest-stamped, one root over
                                                 # all of them.

Stdlib only (ADR-0007).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dynamis_core.canonical import object_hash  # noqa: E402

BRIDGE = "dyn.bridge.v1"
CARD_VERSION = "erc8004-export/1"
GENESIS = "0" * 64


class BridgeError(Exception):
    pass


def erc8004_card(passport) -> dict:
    """ERC-8004-shaped discovery card from an AgentPassport (export-only)."""
    for k in passport.keyrefs:
        if not str(k).startswith("hsm:"):
            raise BridgeError(f"passport {passport.agent_id} carries raw key material — refused")
    card = {
        "version": CARD_VERSION,
        "identity": {
            "agent_id": passport.agent_id,
            "persona": passport.persona,
            "keyproof_fp": object_hash({"keyrefs": passport.keyrefs})[:16],
        },
        "capabilities": list(passport.capabilities),
        "reputation": {
            "census_day": passport.census_day,
            "wallet_ref": passport.wallet,
        },
    }
    card["card_digest"] = object_hash({k: v for k, v in card.items()
                                       if k != "card_digest"})[:32]
    return card


def export_cards(passports: list) -> dict:
    """Cards + offline-verifiable manifest (sorted-card canonical root)."""
    if not passports:
        raise BridgeError("nothing to export")
    cards = [erc8004_card(p) for p in passports]
    ids = [c["identity"]["agent_id"] for c in cards]
    if len(set(ids)) != len(ids):
        raise BridgeError("duplicate agent ids in export set")
    root = object_hash({"sorted_digests": sorted(c["card_digest"] for c in cards),
                        "count": len(cards)})[:32]
    manifest = {
        "bridge": BRIDGE, "count": len(cards),
        "root": root, "genesis": GENESIS,
        "verify": "digest = sha256 of canonical JSON (sorted keys, no "
                  "whitespace, UTF-8) truncated to 32 hex chars; root over "
                  "the sorted card digests + count by the same rule; no "
                  "runtime needed",
    }
    return {"manifest": manifest, "cards": cards}


def sample_passports() -> list:
    """The self-contained sample passports (no runtime imports beyond hash)."""
    from dynamis_core.objects import AgentPassport
    return [
        AgentPassport("agent-alpha", "alpha operator", ("hsm:k1",),
                      ("post.dyn.v1", "verify.classB"), "pw-alpha", 12),
        AgentPassport("agent-beta", "beta operator", ("hsm:k2",),
                      ("work.escrow", "verify.classC"), "pw-beta", 12),
    ]


SURFACES_BUNDLE = "discovery-surfaces/1"

# skill → the capability that exercises it + the wire schema governing the
# exchange. Declared once, here. Holders are *derived* from the exported cards;
# a skill no card can exercise refuses the whole bundle — the package cannot
# advertise what no exported agent can do.
SKILL_MAP = {
    "buy_job": {"capability": ("work.escrow",),
                "wire_schema": "schemas/job.schema.json"},
    "settle_by_evidence": {"capability": ("verify.classB", "verify.classC"),
                           "wire_schema": "schemas/claim.schema.json"},
    "publish_receipt": {"capability": ("post.dyn.v1",),
                        "wire_schema": "schemas/receipt.schema.json"},
}
BUNDLE_SCHEMAS = ("job.schema.json", "claim.schema.json",
                  "receipt.schema.json", "post.schema.json")


def build_surfaces(passports: list, schemas_dir: Path) -> dict:
    """The full discovery bundle with a root over every artifact digest."""
    export = export_cards(passports)
    from dyn_x402 import CARD as a2a          # the one source of the A2A card
    caps_by_id = {c["identity"]["agent_id"]: c["capabilities"]
                  for c in export["cards"]}
    digest_by_id = {c["identity"]["agent_id"]: c["card_digest"]
                    for c in export["cards"]}
    skills = []
    for s in a2a["skills"]:
        m = SKILL_MAP.get(s["id"])
        if not m:
            raise BridgeError(f"A2A skill {s['id']!r} has no SKILL_MAP entry "
                              f"— the package would advertise what is undeclared")
        caps = m["capability"]
        holders = sorted(a for a, cs in caps_by_id.items()
                         if any(cap in cs for cap in caps))
        if not holders:
            raise BridgeError(f"skill {s['id']!r}: no exported card holds "
                              f"{list(caps)} — nothing to publish")
        skills.append({
            "id": s["id"], "name": s["name"], "description": s["description"],
            "capability": list(caps), "wire_schema": m["wire_schema"],
            "holders": holders,
            "holder_card_digests": [digest_by_id[a] for a in holders],
        })
    skill_pkg = {"version": "dyn.skills.v1", "protocol": a2a["protocol"],
                 "skills": skills}
    files = {
        "erc8004-cards.json": export,
        "a2a-agent-card.json": a2a,
        "skills.json": skill_pkg,
    }
    for name in BUNDLE_SCHEMAS:
        p = Path(schemas_dir) / name
        if not p.exists():
            raise BridgeError(f"wire schema missing: {p}")
        files[f"schemas/{name}"] = json.loads(p.read_text(encoding="utf-8"))
    artifacts = {path: object_hash(obj)[:32] for path, obj in files.items()}
    root = object_hash({"artifacts": [[k, artifacts[k]]
                                      for k in sorted(artifacts)]})[:32]
    manifest = {
        "bridge": BRIDGE, "bundle": SURFACES_BUNDLE, "count": len(artifacts),
        "artifacts": artifacts,
        "root": root, "genesis": GENESIS,
        "verify": "digest per artifact = sha256 of canonical JSON (sorted "
                  "keys, no whitespace, UTF-8) truncated to 32 hex chars; "
                  "root over the sorted (path, digest) pairs by the same "
                  "rule; no runtime needed",
    }
    return {"manifest": manifest, "artifacts": files}


def write_surfaces(bundle: dict, out_dir: Path) -> None:
    """Write the bundle as a directory; manifest.json is written last."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, obj in sorted(bundle["artifacts"].items()):
        f = out_dir / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(bundle["manifest"], indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.bridge.v1 — gate 3.5 executable")
    ap.add_argument("cmd", choices=["export", "surfaces"])
    ap.add_argument("out", nargs="?", default="-")
    ns = ap.parse_args(argv)
    if ns.cmd == "export":
        out = export_cards(sample_passports())
        text = json.dumps(out, indent=2)
        if ns.out == "-":
            print(text)
        else:
            Path(ns.out).write_text(text, encoding="utf-8")
            print(f"wrote {ns.out}: {out['manifest']['count']} cards, root {out['manifest']['root']}")
    elif ns.cmd == "surfaces":
        if ns.out == "-":
            raise SystemExit("surfaces needs a directory (use '-' only with export)")
        schemas_dir = Path(__file__).resolve().parent.parent / "schemas"
        bundle = build_surfaces(sample_passports(), schemas_dir)
        write_surfaces(bundle, Path(ns.out))
        m = bundle["manifest"]
        print(f"wrote {ns.out}: {m['count']} artifacts, root {m['root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
