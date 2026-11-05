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
        "verify": "recompute object_hash over sorted card digests; no runtime needed",
    }
    return {"manifest": manifest, "cards": cards}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dyn.bridge.v1 — gate 3.5 executable")
    ap.add_argument("cmd", choices=["export"])
    ap.add_argument("out", nargs="?", default="-")
    ns = ap.parse_args(argv)
    if ns.cmd == "export":
        # Self-contained sample passports (no runtime imports beyond canonical hash).
        from dynamis_core.objects import AgentPassport
        samples = [
            AgentPassport("agent-alpha", "alpha operator", ("hsm:k1",),
                          ("post.dyn.v1", "verify.classB"), "pw-alpha", 12),
            AgentPassport("agent-beta", "beta operator", ("hsm:k2",),
                          ("work.escrow", "verify.classC"), "pw-beta", 12),
        ]
        out = export_cards(samples)
        text = json.dumps(out, indent=2)
        if ns.out == "-":
            print(text)
        else:
            Path(ns.out).write_text(text, encoding="utf-8")
            print(f"wrote {ns.out}: {out['manifest']['count']} cards, root {out['manifest']['root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
