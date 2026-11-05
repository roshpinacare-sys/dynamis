"""RC² — inference credits (docs/03 §3, genesis#rc2).

Stake DYN → accrue credits → spend on model calls. Credits regenerate with time and
stake; they cannot be bought at scale without adding stake (genesis#rc2). All integers:
credits are ERG-micro units (µERG). Accrual is stake-weighted with a cap of
CAP_DAYS days of full-rate accrual — hoarding is bounded, so RC² stays a usage meter,
not a speculative asset.
"""
from __future__ import annotations

from .objects import PowerAccount

# Parameters — labeled estimates until Gate 2.3 measures the actual call mix.
# rate (µERG/day) = stake_dyn_mu // ACCRUAL_DIVISOR  → 1 DYN staked = 0.1 ERG/day.
ACCRUAL_DIVISOR = 10
CAP_DAYS = 7


def daily_rate_muerg(stake_dyn_mu: int) -> int:
    return stake_dyn_mu // ACCRUAL_DIVISOR


def accrue(account: PowerAccount, days: int = 1) -> int:
    """Daily accrual toward the stake cap. Returns credits added (integer)."""
    if days < 0:
        raise ValueError("days moves forward only")
    rate = daily_rate_muerg(account.stake_dyn_mu)
    if rate == 0:
        return 0
    cap = rate * CAP_DAYS
    added = 0
    for _ in range(days):
        if account.erg_credits >= cap:
            break
        step = min(rate, cap - account.erg_credits)
        account.erg_credits += step
        added += step
    return added


def spend(account: PowerAccount, erg_mu: int) -> None:
    """Burn credits for model calls. Deny-by-default: no credit, no call."""
    if not isinstance(erg_mu, int) or isinstance(erg_mu, bool) or erg_mu <= 0:
        raise ValueError("spend must be a positive integer of µERG")
    if account.erg_credits < erg_mu:
        raise ValueError(
            f"insufficient RC²: have {account.erg_credits} µERG, need {erg_mu} µERG "
            "(add stake — credits are not purchasable at scale, genesis#rc2)")
    account.erg_credits -= erg_mu


def stake_factor(account: PowerAccount) -> int:
    """Influence weight for witness VRF and market ordering: integer square root of
    whole DYN staked — no floats cross the wire (ADR-0007)."""
    whole_dyn = account.stake_dyn_mu // 1_000_000
    if whole_dyn <= 0:
        return 0
    r = whole_dyn
    while r * r > whole_dyn:            # Newton, integers only
        r = (r + whole_dyn // r) // 2
    return max(r, 1)
