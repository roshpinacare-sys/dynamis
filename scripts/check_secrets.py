#!/usr/bin/env python3
"""Secret scanner — the local half of the repo's secrets hygiene.

Runs in CI on every push (see .github/workflows/ci.yml) and before any commit
you care about: `python3 scripts/check_secrets.py`. It scans every tracked file
for high-signal credential shapes and refuses to pass if one appears.

Deliberate policy: high-signal patterns only (real token shapes, private-key
headers, URL-embedded credentials). Broad heuristics produce false positives
that train humans to ignore the scanner — the one failure mode that matters.
Findings are reported by file and line WITHOUT echoing the matched content.

What this protects: the root's keys never touch git in any form (Law 16).
Key material lives in the census vaults and the HSM (:3057); the repo holds
keyref fingerprints only. Enforcement pairs with GitHub-side secret scanning
+ push protection (docs/10-secrets-and-vault.md §3).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

# Detector-fixture allowance — one source of truth, imported from census.py.
# Files whose PURPOSE is carrying synthetic credential shapes for the detector
# tests. Always named in the scan's output; nothing else is exempt. This keeps
# the scanners able to test themselves without ever going quiet about it.
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from census import ALLOWED_FIXTURES  # noqa: E402

# (label, pattern) — high-signal credential shapes only.
PATTERNS = [
    ("github fine-grained PAT", re.compile(r"github_pat_[A-Za-z0-9_]{18,}")),
    ("github classic token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{25,}\b")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("url-embedded credential", re.compile(r"://[^/\s:@]+:[^/\s@]{8,}@")),
    ("slack-style token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("openai-style api key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
]

# Filenames that must never be tracked, whatever their contents.
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".secret")

GITIGNORE_GUARDS = ["*.key", ".env", ".secret"]


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO,
                         capture_output=True, check=True)
    return [REPO / p for p in out.stdout.decode().split("\0") if p]


def is_binary(blob: bytes) -> bool:
    return b"\0" in blob[:8192]


def main() -> int:
    findings: list[str] = []
    fixtures: list[str] = []
    files = tracked_files()
    for path in files:
        if path.resolve() == SELF:
            continue
        rel = str(path.relative_to(REPO))
        if rel in ALLOWED_FIXTURES:
            fixtures.append(rel)
            continue
        name = path.name
        if name in FORBIDDEN_NAMES or name.endswith(FORBIDDEN_SUFFIXES):
            findings.append(f"{path.relative_to(REPO)}: forbidden filename committed")
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        if is_binary(blob):
            continue
        for lineno, line in enumerate(blob.decode("utf-8", "replace").splitlines(), 1):
            for label, pat in PATTERNS:
                if pat.search(line):
                    findings.append(f"{path.relative_to(REPO)}:{lineno}: {label}")

    # .gitignore must keep guarding the classic leak paths.
    gi = REPO / ".gitignore"
    if gi.exists():
        text = gi.read_text()
        for guard in GITIGNORE_GUARDS:
            if guard not in text:
                findings.append(f".gitignore: missing guard for {guard}")
    else:
        findings.append(".gitignore: missing entirely")

    if findings:
        print(f"SECRET SCAN FAILED — {len(findings)} finding(s):")
        for f in findings:
            print(f"  {f}")
        print("The matched content is not printed here. Remove the secret from the")
        print("file, rotate the credential at its provider, and see docs/10 §5.")
        return 1
    print(f"secret scan: clean ({len(files) - len(fixtures)} files scanned, "
          f"{len(fixtures)} allowlisted detector fixture(s): "
          f"{', '.join(fixtures) or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
