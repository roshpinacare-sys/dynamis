# Security Policy

## Reporting a vulnerability

Open a GitHub security advisory (**Security → Report a vulnerability**) — private by
default. Do not open a public issue for anything that touches key material, the
signing path, or emission. You will get a response inside one working day; if the
report is accepted, the fix ships before any public disclosure.

## The one rule that matters

Key material never enters this repository or any public network in any form
(CANON Law 16). Keys live in the estate's census vaults and are used only through
the HSM (`:3057`, deny-by-default). This repo holds **keyref fingerprints** — never
keyrefs themselves, never keys. The full custody model: `docs/10-secrets-and-vault.md`.

## What is already armed

- Secret scanning + push protection on this repo (GitHub-side, blocks credential pushes).
- `scripts/check_secrets.py` runs in CI on every push: tracked files are scanned for
  credential shapes; a leak fails the build.
- `.gitignore` guards `*.key`, `*.pem`, `.env`, `*.secret`, vault/ and secrets/ paths.
- Branch protection on `main`: force pushes and deletions refused.
- Dependabot alerts + security updates enabled.

## Handling a leaked credential (runbook summary)

1. Revoke/rotate at the provider — first, before analysis.
2. Remove from the branch; if it reached history, rewrite (`git filter-repo`) and
   force-push — permitted here because `main` history is policy, not audit (the
   append-only audit trail lives in the estate ledger, not in git).
3. Assess the exposure window from provider logs; state it plainly in the incident note.
4. Full procedure and tiers: `docs/10-secrets-and-vault.md` §5.
