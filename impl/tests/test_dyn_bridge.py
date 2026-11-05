"""Gate 3.5 — ERC-8004 export bridge: offline discovery, zero runtime dependency."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dyn_bridge import BridgeError, erc8004_card, export_cards
from dynamis_core.canonical import object_hash
from dynamis_core.objects import AgentPassport


def passport(agent_id: str, caps=("work.escrow",)) -> AgentPassport:
    return AgentPassport(agent_id, f"{agent_id} operator", ("hsm:k1",),
                         caps, f"pw-{agent_id}", 12)


class TestBridge(unittest.TestCase):

    def test_card_shape_and_digest(self):
        card = erc8004_card(passport("agent-alpha"))
        self.assertEqual(card["version"], "erc8004-export/1")
        self.assertNotIn("keyrefs", card["identity"])   # key material never exports
        rehash = object_hash({k: v for k, v in card.items() if k != "card_digest"})[:32]
        self.assertEqual(card["card_digest"], rehash)

    def test_manifest_root_verifies_offline(self):
        out = export_cards([passport("agent-alpha"), passport("agent-beta"),
                            passport("agent-gamma")])
        recomputed = object_hash({
            "sorted_digests": sorted(c["card_digest"] for c in out["cards"]),
            "count": len(out["cards"])})[:32]
        self.assertEqual(out["manifest"]["root"], recomputed)

    def test_raw_key_material_refused(self):
        with self.assertRaises(ValueError):          # Law 3 refuses at construction
            AgentPassport("agent-raw", "raw operator", ("RAWKEY",), ("work.escrow",),
                          "pw-raw", 12)
        from types import SimpleNamespace
        stub = SimpleNamespace(agent_id="agent-raw", persona="raw", keyrefs=("RAWKEY",),
                               capabilities=("work.escrow",), wallet="pw-raw", census_day=12)
        with self.assertRaises(BridgeError):         # the bridge refuses again
            erc8004_card(stub)

    def test_duplicate_ids_refused(self):
        with self.assertRaises(BridgeError):
            export_cards([passport("agent-alpha"), passport("agent-alpha")])

    def test_import_isolation(self):
        """No runtime module may import the bridge — the root runs without it."""
        impl_dir = Path(__file__).resolve().parent.parent
        offenders = []
        for py in impl_dir.glob("*.py"):
            if py.name == "dyn_bridge.py":
                continue
            if "dyn_bridge" in py.read_text(encoding="utf-8"):
                offenders.append(py.name)
        for py in (impl_dir / "dynamis_core").glob("*.py"):
            if "dyn_bridge" in py.read_text(encoding="utf-8"):
                offenders.append(py.name)
        self.assertEqual(offenders, [], f"runtime depends on the bridge: {offenders}")


if __name__ == "__main__":
    unittest.main()
