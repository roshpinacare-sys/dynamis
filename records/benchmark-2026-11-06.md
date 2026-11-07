# What the craft loop changes — measured

Seed 20261106 · pool 60 tasks (30 file fingerprints, 30 web rebuilds) · escrow 200 USDS/task · pool value 12,000 USDS

Worker model (stated, not hidden): 30% of builds ship broken (20 of 60 drawn); 50% of those claim “it is correct” (11 forged claims). 40 builds are drawn correct. Every pipeline runs the SAME draws.

| pipeline | shipped broken | working delivered | buyer paid (USDS) | refunded (USDS) | cost / working artifact (USDS) | forged claims caught |
| --- | --- | --- | --- | --- | --- | --- |
| naive — pay everything, verify nothing | 20 | 40 | 12,000 | 0 | 300 | 0 |
| self-report — the worker's claim gates | 20 | 40 | 12,000 | 0 | 300 | 0 |
| craft — study, build, re-executed check | 0 | 40 | 8,000 | 4,000 | 200 | 11 |

Worker income: agent-honest-1 8,000 USDS, agent-shaky-1 0 USDS — broken builds earn zero; correctness is the only income

Protocol overhead, measured on the same run: 175.2 ms per full job (open→study→approval→build→check→settle/refund), 10546 ms total. The chain sealed itself 30× over 360 ledger entries and the audit returned ok=true.

## Reading

- The loop does not make generation smarter: the same draws produce the same builds everywhere. What changes is what survives to the buyer — 20 broken deliveries reach the buyer un-verified; 0 reach it through the check.
- The buyer's cost per working artifact falls from 300 USDS (paying for broken work) to the task's own price — everything else comes back as refunds, fees 0, emission 0.
- Correctness becomes the only income: the honest worker earns everything the shaky worker earns nothing. That is the incentive the protocol adds.
- A claim is not evidence: self-report ships the same broken work as naive and catches none of the forged claims; the re-executed check catches all 11 of them.

## Honest scope

This measures the PROTOCOL's effect under a stated generation-error model, over the loop's real paths and real money. It does not measure model quality — the workers are seeded draws, not agents. Measuring real agents against this pool is the named next measurement; the harness they would face is the same one these numbers came from.
