# 10 · Secrets, vaults, and key custody

This chapter is the repo's half of the estate's custody doctrine. The estate half —
census, two-soul keys, sealed vaults, the HSM — is described in the founding plan and
`docs/01-architecture.md`. Here we answer the operational question: **what touches git,
what touches GitHub, and what touches nothing digital at all** — and how every path is
enforced by machinery, not by promises.

## 1. The three tiers of secret material

| Tier | What | Where it lives | How it is used | Never |
|---|---|---|---|---|
| **0 — root keys** | Two-soul custody keys, census rosters, vault seals | census vaults, offline, sealed | physical ceremony to unseal; census re-verification | in a file, in git, on a networked host |
| **1 — signing keys** | Every key that can move value or sign protocol objects | HSM (`:3057`), deny-by-default | payloads sent to `/sign {keyRef, digestHex}`; the key never leaves the module | exported, backed up as a file, logged |
| **2 — operational tokens** | Scoped capability tokens, CI credentials, API tokens | GitHub **encrypted Actions secrets**, estate secret store | consumed by workflows and adapters; scoped, short-lived, rotated | committed, printed, embedded in URLs |

The design rule behind the tiers: a leak of tier 2 must never enable a move of value;
a move of value requires tier 1, which is physically incapable of leaving the HSM.

## 2. What may appear in this repo

- **Keyref fingerprints** — truncated hashes of key references (as `impl/agent_kit.py`
  builds them: `object_hash({...})[:16]`), never the keyref itself.
- **Capability tokens in examples** — marked as examples, with scope placeholders.
- **`FLEET_GH_TOKEN` as a *name*** — the secret's existence is public (GitHub shows
  names), its value is sealed: encrypted to the repository's public key with a
  libsodium sealed box, decryptable only by GitHub Actions inside this repo.

## 3. The enforcement stack (what is actually armed)

1. **GitHub secret scanning + push protection** — enabled on the repository. If a
   credential shape is pushed, GitHub blocks the push client-side.
2. **`scripts/check_secrets.py` in CI** — scans every tracked file for high-signal
   credential shapes (fine-grained PATs, classic tokens, private-key blocks,
   URL-embedded credentials, AWS/Slack/API-key shapes). A finding fails the build;
   the matched content is never echoed.
3. **`.gitignore`** guards `*.key`, `*.pem`, `*.p12`, `.env`, `*.secret`, `secrets/`,
   `vault/` — plus the CI check asserts the guards stay in place.
4. **Branch protection on `main`** — force pushes and deletions refused. (Git history
   here is engineering convenience, not the audit trail; the append-only record of
   value is the estate ledger. Rewriting git history after a leak is therefore
   permitted and is part of the runbook.)
5. **Dependabot** — alerts + security updates on; Actions versions bumped weekly.
6. **`CODEOWNERS`** — every path owned by the regulator; constitutional files
   (`CANON.md`, `params/`, `specs/gates.yaml`, `specs/wire.md`) flagged explicitly.
7. **Environment `production`** — reserved for future deploy workflows, restricted to
   protected branches once created (requires the token to hold the Environments
   permission); reviewers can be added then for a human gate on production deploys.

## 4. Sealed secrets in GitHub Actions

`FLEET_GH_TOKEN` is stored via the encrypted-secrets API:

```
GET  /repos/roshpinacare-sys/dynamis/actions/secrets/public-key   # repo public key
     -> libsodium sealed box (crypto_box_seal) over the token
PUT  /repos/roshpinacare-sys/dynamis/actions/secrets/FLEET_GH_TOKEN
```

Workflows consume it as `${{ secrets.FLEET_GH_TOKEN }}`. The value is not readable by
humans through the API after sealing — only by Actions runs of this repository. The
scanner deliberately skips no file except itself; the workflow files reference the
secret **by name**, which is public by design.

## 5. Runbooks

**Rotation (scheduled, every 90 days — next: 2027-02-02):**
1. Mint the replacement credential at the provider.
2. Seal it over the old one (`PUT` the same secret name).
3. Re-run the CI suite manually (`workflow_dispatch`).
4. Revoke the old credential. Record the rotation in the ops log — a rotation that is
   not recorded did not happen (Law 4).

**Leak (reactive):**
1. Revoke at the provider — before any analysis.
2. Remove from the branch; if it reached history, `git filter-repo` + force-push.
3. Read the provider's logs to bound the exposure window; write the window down.
4. File the incident note as an ADR appendix if process changes; otherwise ops log.
5. Re-run `scripts/check_secrets.py` — the scanner must be green before the incident
   is considered closed.

## 6. What this deliberately does not do

- It does not put the estate's private ledger, census, or vault contents on GitHub.
  The public repo holds the protocol and its reference implementation; the root's
  books and custody stay private (Law 16).
- It does not use a shared long-lived machine account anywhere. Every automation path
  holds one scoped credential for one purpose, rotated on schedule.
- It does not trust client-side checks alone: GitHub-side push protection is the
  second lock, and the CI scanner is the third.
