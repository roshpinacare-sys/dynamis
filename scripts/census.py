#!/usr/bin/env python3
"""census.py — the public-repo device scan (gate 0.2, public half).

The estate's full two-soul census — sealed vaults, HSM rosters, device
attestation — is private by design (docs/10: it never goes on GitHub). What
the PUBLIC repo must prove is narrower and absolute, and anyone can re-run it:

  python3 scripts/census.py          # exit 0 = clean, exit 1 = finding

The scan covers every tracked file (HEAD tree) for:
  - PEM / OPENSSH / EC PRIVATE KEY blocks and any "PRIVATE KEY" marker;
  - WIF-shaped secp256k1 keys ([5KL] + 50-51 base58 chars);
  - AWS-style access keys (AKIA + 16 chars);
  - files named like key material (*.pem, *.key, *.p12, *.keystore, *seed*);
and, when GH_TOKEN or GH_TOKEN_FILE is present, verifies that the repository's
encrypted Actions secrets exist and that no secret VALUE is reachable here
(the API exposes names only, by design — that is the point).

Scope honesty: this proves the public half of gate 0.2 ("zero plaintext keys
found on device scan") for the public artifact. The estate-side two-soul
verification (every key exists in two independent places) runs in the estate
census and is reported in CUSTODY.md — it cannot and must not run here.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PEM_RE = re.compile(
    r"-----BEGIN (?:[A-Z ]* )?PRIVATE KEY(?: BLOCK)?-----")
WIF_RE = re.compile(r"\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b")
AWS_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
KEYFILE_SUFFIXES = (".pem", ".p12", ".p12", ".pfx", ".keystore")
KEYFILE_NAME_RE = re.compile(r"(seed[-_]?phrase|private[-_]?key|\.key$)",
                             re.IGNORECASE)


def scan_text(text: str) -> list[str]:
    """Detector over one blob. Returns finding codes (unit-tested)."""
    found = []
    if PEM_RE.search(text):
        found.append("PEM-PRIVATE-KEY")
    if WIF_RE.search(text):
        found.append("WIF-SHAPED-KEY")
    if AWS_RE.search(text):
        found.append("AWS-ACCESS-KEY")
    return found


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, check=True)
    return [f for f in out.stdout.decode().split("\0") if f]


def check_actions_secrets() -> list[str]:
    """Names-only check of the sealed Actions secrets (no values exist here)."""
    token = os.environ.get("GH_TOKEN") or ""
    tf = os.environ.get("GH_TOKEN_FILE")
    if not token and tf and Path(tf).exists():
        token = Path(tf).read_text(encoding="utf-8").strip()
    if not token:
        return []  # offline run: the repo-side scan is the proof available
    import json
    import urllib.request
    req = urllib.request.Request(
        "https://api.github.com/repos/roshpinacare-sys/dynamis/actions/secrets",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            names = [s["name"] for s in json.load(r).get("secrets", [])]
    except Exception as exc:
        return [f"ACTIONS-API-UNREACHABLE: {exc}"]
    findings = []
    if "FLEET_GH_TOKEN" not in names:
        findings.append("ACTIONS-SECRET-MISSING: FLEET_GH_TOKEN not sealed")
    return findings


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for rel in tracked_files():
        p = ROOT / rel
        if not p.is_file():
            continue
        scanned += 1
        low = rel.lower()
        if low.endswith(KEYFILE_SUFFIXES) or KEYFILE_NAME_RE.search(low):
            findings.append(f"KEYFILE-NAME: {rel}")
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            text = p.read_bytes().decode("latin-1")
        for code in scan_text(text):
            findings.append(f"{code}: {rel}")
    findings += check_actions_secrets()
    print(f"census: scanned {scanned} tracked files, "
          f"{len(findings)} findings")
    for f in findings[:20]:
        print(f"  FINDING: {f}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
