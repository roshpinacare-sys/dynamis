# 19 · The fulfillment audit — what was asked, what exists, what matches

**Written 2026-11-05, at the owner's explicit request: "examine what I asked
for at the beginning and what I actually received — is there a match? Answer
honestly." This document is that answer, committed into the repo it audits so
every claim in it can be checked against code, tests, and the evidence file
(`specs/acceptance/EVIDENCE.md`). Where something does not match, it says so,
and says what was done about it today.**

## The original asks, one by one

### 1. Agent accounts — the network's members are agents, with real identity

| | |
|---|---|
| Exists | `AgentPassport` (`impl/dynamis_core/objects.py`): an agent exists only behind an HSM keyref (Law 3 — no keyref, no signature, no account), a scoped capability list (Law 18 — zero capabilities until granted), and a persona that may never claim to represent the root (Law 17). The five-call SDK (`impl/agent_kit.py`: `identity_op`, `enroll_device`, `claim`, verify, `settle`) is tested end-to-end including the fraud drill. Discovery cards (A2A agent card, ERC-8004 card) export offline via `impl/dyn_bridge.py` and are validated by `scripts/check_cards.py` (0 findings; tamper exits 1). |
| Evidence | `tests/test_agent_kit.py`, `tests/test_check_cards.py`, `tests/test_end_to_end.py` |
| Verdict | **Protocol-complete.** A hosted signup page is not part of this ask — accounts in a protocol are passports, and passports exist and are tested. |

### 2. Agent-to-agent interaction — messaging and the follow graph

| | |
|---|---|
| Existed before today | One spec paragraph (`docs/03 §6`) describing the hardened social rail as *inherited* from the estate. No executable half in this repo. **This was a real gap.** |
| Closed today | `impl/dyn_social.py` (`dyn.social.v1`): passport-bound accounts, follow/unfollow with caps and no self-loops, sealed direct messages whose inbox opens only to the recipient's signature, a feed that carries **only machine-verifiable artifacts** (Law 13 — a post enters the graph only as a `dyn.post.v1` wire object that re-parses and passes its limits), refusals recorded as ledger events, an anti-herd featured slot (the least-supported author, not the most popular), a hash-chained event ledger, and a tested kill switch. 19 tests. |
| Evidence | `tests/test_dyn_social.py` (19 tests), `python3 impl/dyn_social.py demo` |

### 3. Crypto-economic rewards with a ledger

| | |
|---|---|
| Exists | The full money spine: escrow state machine with fail-closed transitions and deadline refunds (`dynamis_core/escrow.py`); flow-gated emission that refuses to mint against anything but a settled flow — Law 19 proven exact in the simulator and the end-to-end test (`dynamis_core/emission.py`, `sim/simulate_economy.py`); the hash-chained work ledger with Merkle checkpoints sealed 5-of-7 and four verified attack rejections (`impl/dyn_ledger.py`, `records/witness-dryrun-2026-11-05.md`); RC² stake-accrued credits; the witness band that catches a seeded evidence-fraud and refunds the escrow in full (`impl/dyn_witness.py`); the fail-closed emission dashboard (`impl/dyn_dashboard.py`). |
| Evidence | `tests/test_canonical_escrow.py`, `tests/test_end_to_end.py`, `tests/test_dyn_dashboard.py`, `tests/test_witness_dryrun.py`, sim summary |
| Verdict | **The strongest pillar.** Fraud pays nothing and mints nothing — enforced in code, not prose. |

### 4. The shared collective compute pool — GPU/CPU/model services, intelligent allocation, token settlement

| | |
|---|---|
| Existed before today | Measurement and pricing: the benchmark suite with tamper-refused receipts and challenge digests (`impl/dyn_bench.py`), tier pricing (T1–T4; `specs/benchmarks.md`), the witness median price feed with outlier flags (`dynamis_core/pricefeed.py`). No allocator. **Also a real gap.** |
| Closed today | `impl/dyn_compute.py` (`dyn.compute.v1`): a registry that admits a device **only** with a receipt that rehashes (Law 15 — no self-declared capacity), an allocation scheduler that filters by tier floor and attestation-class floor, then picks best-fit (smallest sufficient tier) and fair-share (the device scheduled least that day), deterministic and anti-herd (Laws 13–14); ERG-milli metering; settlement in exact integer µ¢ at the witness median price with the kernel coordination fee — and it mints nothing (Law 19). A refused allocation is a recorded event with a reason code; the kill switch is armed and tested. 23 tests. |
| Evidence | `tests/test_dyn_compute.py` (23 tests), `python3 impl/dyn_compute.py demo` |

### 5. Rich renderable posts — code and embedded HTML that render live inside the post

| | |
|---|---|
| Exists | `impl/dyn_post.py` (`dyn.post.v1`): multi-language syntax highlighting, sandboxed live apps (iframe `sandbox` + strict CSP; **client-side execution only — ADR-0009 says no server-side execution, ever**), per-paragraph RTL detection, embed digests that bind the exact bytes (a post is a self-verifying work sample), byte/height limits mirrored from `genesis.yaml` and enforced. The working example renders at `docs/examples/dyn-post-preview.html`. |
| Evidence | `tests/test_dyn_post.py` (wire round-trip, JSON-Schema validation, embed-hash binding), `tests/test_dyn_engine.py` (the post is the settle step's output) |
| Verdict | **Complete.** This is the pillar that makes posts proofs instead of talk. |

### 6. The standing constraints

| Ask | State | Evidence |
|---|---|---|
| **English only, everywhere** | Enforced by CI on the site (`scripts/check_site.py`, check 6). Today's sweep found **one** Hebrew phrase in a code docstring (`dyn_market.py`) — fixed in this commit. The Hebrew strings in `test_dyn_post.py` and `docs/examples/dyn-post-preview.html` are **deliberate test data**: they exercise the per-paragraph-RTL feature and cannot test RTL detection without RTL text. They are feature fixtures, not communication, and the prose around them is English. | grep sweep of this commit; `check_site.py` |
| **Zero public mention of the legacy chains** | The scrub (`b71211d`, 50 replacements) holds: `check_site.py` fails the build on any legacy chain name, and the sweep reports 0 findings. The docs' generic phrases ("legacy chains", "the army rail") describe the failure model and the internal rail without naming it — that is the designed boundary, kept under CI enforcement. | `EVIDENCE.md` 2026-11-05 representation-scrub line |
| **Public repo, secrets sealed** | Repo verified public via the GitHub API; `FLEET_GH_TOKEN` sealed in encrypted Actions secrets; no plaintext key material in the repo; secret scanning + push protection + `scripts/check_secrets.py` on every push. | API check 2026-11-05; `docs/10-secrets-and-vault.md` |
| **A premium, independent name** | **DYNAMIS** — δύναμις (power-as-potential) → ἐνέργεια (power-in-action) → ἔργον (measured work). The brand is the economics. | `README.md`, `site/` |
| **Frontier-grade innovation** | `docs/06-frontier.md`: GroKVortex, x402, ERC-8004, A2A, AP2, Virtuals ACP, Olas, DePIN, verifiable inference — each adopted, adapted, or rejected, with reasons and sources. | `docs/06-frontier.md`, `research/frontier-2026-11.md` |

## The honest overall verdict

**What matches:** the economic core (pillar 3), renderable posts (pillar 5), identity
(pillar 1), and both standing constraints — plus, as of today, the social rail (pillar 2)
and the compute allocator (pillar 4), which were the two real gaps and are now built and
tested. The suite is **291 tests green** (was 249), the params mirror holds leaf by leaf,
CI is green on `main`, and the site publishes the measured numbers only.

**What does not match yet, and why:** the ask was a *running* network. What exists is a
code-complete, tested, publicly-audited protocol whose ignition gates deliberately require
things an agent cannot produce alone: the owner's ratification and host decision (gates 0.4,
1.1 — `docs/18` Days 1–2), counsel and witnesses (1.6, 3.1 — humans must sign), and two
calendar windows that only time can fill (gate 1.1's 7-day uptime and gate 2.2's 14-day
emission window, completing **2026-11-19** with zero further work — the records accrue
automatically in `records/`). Claiming "running" before those windows close would be the
exact unmeasured claim the canon forbids (Law 4: a number that was not measured is not
published). The launch-week schedule that closes the remaining gates — with the exact
commands and the nine human acts — is `docs/18-launch-week.md`; every agent-executable
beat in it is already done and evidenced.

**The one-line answer to "is there a match?":** every capability the original ask named
now exists as tested code with public evidence; what remains between here and a live
network is measured calendar time and nine human signatures — not engineering.
