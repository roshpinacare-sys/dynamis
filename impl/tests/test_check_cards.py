"""The card validator: an export set is valid, or the finding says why."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from check_cards import samples_export, validate  # noqa: E402
from dyn_bridge import BridgeError, export_cards  # noqa: E402
from dynamis_core.objects import AgentPassport  # noqa: E402


class TestCheckCards(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.export = samples_export()

    def test_sample_set_is_valid(self):
        self.assertEqual(validate(self.export), [])

    def test_edited_card_is_caught(self):
        """Change one field after export → the digest stops recomputing."""
        tampered = copy.deepcopy(self.export)
        tampered["cards"][0]["identity"]["persona"] = "impostor"
        fails = validate(tampered)
        self.assertTrue(any("card_digest does not recompute" in f
                            for f in fails))

    def test_edited_set_is_caught_by_root(self):
        """Swap in a different card set → manifest root mismatch."""
        other = export_cards([AgentPassport(
            "agent-gamma", "gamma operator", ("hsm:k3",),
            ("post.dyn.v1",), "pw-gamma", 12)])
        tampered = {"manifest": dict(self.export["manifest"]),
                    "cards": other["cards"]}
        fails = validate(tampered)
        self.assertTrue(any("manifest root mismatch" in f for f in fails))
        self.assertTrue(any("manifest.count" in f for f in fails))

    def test_malformed_id_and_duplicate_ids(self):
        bad = copy.deepcopy(self.export)
        bad["cards"][0]["identity"]["agent_id"] = "Bad_ID"
        self.assertTrue(any("id malformed" in f for f in validate(bad)))
        with self.assertRaises(BridgeError):
            export_cards([AgentPassport("agent-alpha", "op", ("hsm:k1",),
                                        ("post.dyn.v1",), "pw-one", 12),
                          AgentPassport("agent-alpha", "op", ("hsm:k2",),
                                        ("post.dyn.v1",), "pw-two", 12)])

    def test_surfaces_bundle_valid(self):
        import tempfile
        from check_cards import validate_surfaces
        from dyn_bridge import build_surfaces, write_surfaces
        schemas = Path(__file__).resolve().parent.parent.parent / "schemas"
        bundle = build_surfaces(
            [AgentPassport("agent-alpha", "alpha operator", ("hsm:k1",),
                           ("post.dyn.v1", "verify.classB"), "pw-alpha", 12),
             AgentPassport("agent-beta", "beta operator", ("hsm:k2",),
                           ("work.escrow", "verify.classC"), "pw-beta", 12)],
            schemas)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "discovery"
            write_surfaces(bundle, out)
            self.assertEqual(validate_surfaces(out), [])

    def test_surfaces_tamper_caught(self):
        import json
        import tempfile
        from check_cards import validate_surfaces
        from dyn_bridge import build_surfaces, write_surfaces
        schemas = Path(__file__).resolve().parent.parent.parent / "schemas"
        bundle = build_surfaces(
            [AgentPassport("agent-alpha", "alpha operator", ("hsm:k1",),
                           ("post.dyn.v1", "verify.classB"), "pw-alpha", 12),
             AgentPassport("agent-beta", "beta operator", ("hsm:k2",),
                           ("work.escrow", "verify.classC"), "pw-beta", 12)],
            schemas)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "discovery"
            write_surfaces(bundle, out)
            f = out / "skills.json"
            obj = json.loads(f.read_text(encoding="utf-8"))
            obj["skills"][0]["holders"] = ["agent-ghost"]
            f.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
            fails = validate_surfaces(out)
            self.assertTrue(any("digest mismatch" in x for x in fails))
            self.assertTrue(any("holder" in x for x in fails))


if __name__ == "__main__":
    unittest.main()
