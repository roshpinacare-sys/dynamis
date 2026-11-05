"""Tests: scripts/census.py — the public-repo device scan (gate 0.2, public half).

The detectors must catch real key material shapes, must not flag honest
content, and the actual repository scan must exit clean — the repo's own
claim of zero plaintext keys is re-proven on every test run.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from census import scan_text  # noqa: E402


class TestDetectors(unittest.TestCase):
    def test_pem_block_is_found(self):
        text = "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----"
        self.assertIn("PEM-PRIVATE-KEY", scan_text(text))

    def test_wif_shape_is_found(self):
        wif = "5K" + "H" * 50            # [5KL] + 50 base58 chars
        self.assertIn("WIF-SHAPED-KEY", scan_text(f"key={wif}"))

    def test_aws_key_is_found(self):
        self.assertIn("AWS-ACCESS-KEY", scan_text("id AKIAABCDEFGHIJKLMNOP"))

    def test_honest_content_is_clean(self):
        clean = ("digest 000000...ff, sha256 over canonical body, "
                 "receipt hash b" * 64 + "  # base58-ish but not a key")
        self.assertEqual(scan_text(clean), [])
        self.assertEqual(scan_text("the archive holds the curation records"), [])

    def test_word_boundary_no_false_positive_on_archive(self):
        self.assertEqual(scan_text("archive achieve"), [])


class TestRepoScan(unittest.TestCase):
    def test_the_repository_itself_is_clean(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "census.py")],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("0 findings", out.stdout)


if __name__ == "__main__":
    unittest.main()
