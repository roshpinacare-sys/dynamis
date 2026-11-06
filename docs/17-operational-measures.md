# 17 · Operational measures — gates 1.1, 1.2, 2.2, 3.3 executable

Four more packages close their in-repo half. What remains for each gate is
world, not code: devices, hosts, calendar days (docs/05, docs/16 §What-still-gates).

| Module | Gate | The loop it closes |
|---|---|---|
| `impl/dyn_bench.py` | 1.2 | the benchmark suite (attestation class B) — measured receipts, tiered T1–T4 from the measurement, tampered receipts refused, L2 challenge digests issued |
| `impl/dyn_dashboard.py` | 2.2 | the honest emission dashboard — Law 19 recomputed from a real stream, **refuses to render a passing dashboard if the invariant breaks** |
| `impl/dyn_fleet.py` | 3.3 | the entity fleet — ≥ 3 entities from template, shared crew pool, capital-committee cadence, a consolidated view that is read-only *by proof* (book digests asserted unchanged) |
| `scripts/heartbeat.py` + `uptime.yml` | 1.1 | the uptime *measurement mechanism* — a 15-minute heartbeat over the core loops; run history is the record, `uptime_report.py` reads it off the API |

## 1.2 · Capacity is a measured receipt, never a claim

A device runs three deterministic kernels (merkle build, hash chain, exact bps
splits) on an identical work budget; the receipt carries wall-time and a
throughput proxy, stamps the tier the measurement supports, and rehash-verifies.
A tampered receipt — inflated throughput, mismatched tier — is refused before
any challenge runs. The L2 challenge client re-derives expected kernel digests
from the receipt's own inputs and demands the device reproduce them:

```bash
python3 impl/dyn_bench.py run dev-001
# receipt: throughput 2,307,692 µ-steps/s → tier T4; challenge digests issued
```

## 2.2 · The dashboard that can lie is not a dashboard

`dyn_dashboard.compute` replays a market stream: settled revenue is payout + fee
(the whole escrow that moved), expected emission is revenue × the canonical rate
(400 µDYN/µ¢), and refunds must emit exactly zero. Any divergence raises — the
HTML is only rendered from a stream where the invariant *holds*:

```bash
python3 impl/dyn_market.py run --days 14 --out market.jsonl
python3 impl/dyn_dashboard.py from-stream market.jsonl --out dashboard.html
# invariant holds, emitted 2,436,000,000,000 µDYN on 6,090,000,000 µ¢ verified revenue
```

The page shows measured numbers beside the canonical rate, and the checks
section names what was measured — the gaps-unhidden rule (docs/02) as HTML.
Gate 2.2's 14-day window is calendar time; this page is the artifact each day
appends to.

## 3.3 · The fleet rolls up to a read-only regulator view

Entities come from the Law-20 template with separate books; a shared crew pool
round-robins employment across them (one pool, many employers); a capital
committee records its T2 review sessions on a 30-day cadence. The consolidated
view sums per-entity revenue and cash and **enforces that the rollup equals the
sum of the parts** — and proves it is read-only by comparing every source book's
journal digest before and after the view runs. A fleet below three entities
refuses to consolidate.

```bash
python3 impl/dyn_fleet.py view ent-001 ent-002 ent-003
# rollup: revenue 720,000,000 µ¢ across 3 balanced books, digests unchanged
```

## 1.1 · Uptime is measured, not declared

The heartbeat runs the fast core loop — integer money, an escrow transition
refused from OPEN, a 24-entry ledger with a sealed 5-of-7 checkpoint — and exits
non-zero on any failure. The `uptime` workflow runs it every 15 minutes on
GitHub Actions; each run is one beat of the 7-day record, and
`scripts/uptime_report.py` computes the percentage from run history:

```bash
python3 scripts/heartbeat.py          # {"ok": true, checks: …}
GITHUB_TOKEN=… python3 scripts/uptime_report.py   # beats, uptime_bps (integer, 10000 = 100.00%), gate verdict
```

The harness ships now; the ≥ 99% number accrues over seven days of real beats —
which is exactly what "measured, not declared" means in practice.
