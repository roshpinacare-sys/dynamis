# Benchmarks — measuring capacity so the pool can advertise only truth

Law 5 (consensus-verifiable capacity) and Law 15 (no self-declared capacity) demand a
measured link between what a device claims and what the pool advertises. This is the
methodology; the executable tiering lands as gate package 1.2.

## 1. What is measured at enrollment

Every device runs the benchmark suite locally on the runner kit (`:3020`), producing
signed receipts (domain `dyn.receipt.v1`). The suite, per device:

| # | Measure | Unit | Why |
|---|---|---|---|
| 1 | tokens/s, 7B-class model (quantized) | tok/s | the fleet's serving class (vLLM/llama.cpp) |
| 2 | tokens/s, 13B-class model (quantized) | tok/s | headroom tier |
| 3 | cold-start to first token | s | interactive-job latency budget |
| 4 | CPU-only tokens/s (small model) | tok/s | the free CI lane and CPU-only members |
| 5 | sustained 30-min throughput decay | % | thermal honesty — burst numbers lie |
| 6 | concurrent sessions before SLA breach | count | multi-tenant capacity |
| 7 | uptime heartbeat history | 30 days | census-adjacent: the machine that is never up advertises nothing |

The receipt binds results to device identity + census state. Results without a receipt
do not exist (Law 4).

## 2. Tiering

Tiers derive mechanically from measured medians across enrolled devices — no
hand-tuning, no "soon":

| Tier | Rule (median over runs) | Advertised capacity |
|---|---|---|
| T-GPU1 | ≥ 10 tok/s sustained @ 7B | 1 ERG/min reserved |
| T-GPU2 | ≥ 25 tok/s sustained @ 7B | 2 ERG/min |
| T-GPU3 | ≥ 25 tok/s @ 13B | 4 ERG/min |
| T-CPU | CPU-only ≥ 5 tok/s small model | 0.25 ERG/min (CPU lane) |
| T-NONE | fails or no receipts | not advertised — at all |

ERG is the reference GPU-minute (genesis); the tier maps device-minutes → ERG at the
witness price feed's rate (impl/`pricefeed.py`).

## 3. Staying honest after enrollment

- **Sampled re-execution** (ladder class C) re-runs a deterministic slice of claimed
  work on a second device; mismatch → dispute path of the state machine.
- **Scheduled spot checks**: the challenge client re-benchmarks a random 10% of
  devices monthly (mulberry32-seeded, reproducible post-hoc — Law 14 discipline).
- **Decay handling**: sustained-decay > 20% drops the tier automatically; the device
  re-earns its tier by re-benchmarking. Advertising capacity the receipts no longer
  support is a slashing event for the operator, measured and published (Law 8).
- **Tie to fraud economics**: fake-capability enrollment is ladder class B fraud; its
  expected profit is negative by construction (`floor_class`), and the sim tracks the
  margin (sim/fig2).

## 4. Job-type registry

Benchmark tiers gate which job verification classes a worker may claim; job types gate
which specs a worker may claim. A job type registers with:

```yaml
job_type: process_invoices
input_schema: schemas/types/invoice-batch.json   # wire-validatable
output_contract: schemas/types/invoice-results-v1.json
default_class: C                                  # money jobs default to C (genesis)
benchmark_ref: receipts of the qualification run  # Law 4
```

The registry is content-addressed; registering a type is itself a class-A verifiable
act (schema checks), so the registry cannot fill with unverifiable promises.

## 5. ERG pricing worked example (integers, µ¢)

Witness feed median: 30,000 µ¢/ERG ($1.80/GPU-hour). A T-GPU2 device reserves
2 ERG/min. A 20-minute inference job quotes: 40 ERG × 30,000 = 1,200,000 µ¢ = **$1.20**
(`erg_to_usds_muc(40, 30_000)` — tested). The fleet's owned-metal cost basis is the
low edge of the DePIN band (frontier §6); the honest price advantage the network claims
is the one the receipts actually show.
