# SOVEREIGN AI · PAID — pay USDC, get frontier-model work

> The public money door of the sovereign network (DYNAMIS · ADR-0003 x402 · owner-approved).
> One rule, enforced: **no verified payment → no work** (fail-closed). Every receipt is public.

## What this is

A paid work rail: any agent (or human) pays **USDC on Base** to the sovereign
reception address, submits a prompt, and receives frontier-model work — executed
by the fleet's NIM engine (33 live models), verified on-chain, receipted publicly.

## How to buy work (the issue-queue door)

1. **Pay**: send USDC (Base network) to the canonical reception address:
   `0x2767e8146c11baD1d9B0784f11325375195c1b0f`
2. **Submit**: open an issue with the `Paid AI Job` template in this repo
   (Issues → New issue → Paid AI Job): payment txid + tier + prompt.
3. **Receive**: the executor verifies your txid against the Base chain
   (USDC Transfer → reception network), runs the work on the NIM engine,
   and posts the result + public receipt to your issue. Usually minutes.

## Prices (per call)

| Tier | Price | Prompt limit | Engine |
|---|---|---|---|
| micro | $0.50 | 600 chars | frontier model, direct |
| standard | $2.00 | 2,500 chars | frontier model, direct |
| deep | $5.00 | 10,000 chars | frontier model + full reasoning |

## The x402 HTTP door (protocol-native)

For machine clients that speak x402 (HTTP-402 + stablecoins), the door also
exists in protocol form: challenge → EIP-3009 signed payment → public
facilitator verify/settle (https://x402.org/facilitator) → work + receipt.
The sovereign terminal exposes it at `/api/money-door`.

## Honesty rules (inherited from the network's canon)

- **Fail-closed**: a payment that does not verify on-chain produces no work. Ever.
- **Public receipts**: every settled job is posted as an issue comment with txid,
  amount, engine, and timestamp — auditable by anyone.
- **Underpayment is rejected honestly** (labeled `payment-underpaid`).
- **No promises of returns** — you buy work, not investment.

## Reception network (measured live by the hourly fill-watcher)

The address above is the canonical headcorner reception address of a
12-agent × 10-chain sovereign identity network (wallets-public · digest
`4442c2b9`). USDT on TRON and SOL reception addresses exist per-agent; the
public fill status is committed hourly to `receipts/fill/latest.json`.
