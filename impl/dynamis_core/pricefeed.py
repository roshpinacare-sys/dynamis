"""Witness price feed — the ERG anchor (docs/03 §2, genesis#witnesses.price_feed_sources).

Witnesses sample DePIN spot medians (io.net H100-hour, Akash, Render) plus the fleet's
measured serving cost, normalized at collection time to µ¢ per ERG (1 ERG = 1
reference GPU-minute). The band medianizes; any witness whose sample deviates more
than `band_bps` from the median is flagged for bond burn (slashing is measured and
reported, Law 8 — this module returns the flags, the chain applies them).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .canonical import check_int_amount

BAND_BPS = 2500  # ±25% around the median, generous until measured data exists


def _median(values: list[int]) -> int:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) // 2  # integer average of the two middles


@dataclass
class PriceRound:
    day: int
    samples_muc: dict[str, int]          # witness_id -> sampled µ¢ per ERG
    median_muc: int = 0
    outliers: dict[str, int] = field(default_factory=dict)  # witness -> deviation bps
    accepted: list[str] = field(default_factory=list)


def collect_round(day: int, samples_muc: dict[str, int], band_bps: int = BAND_BPS) -> PriceRound:
    """One price-feed round. Fails closed: fewer than 3 live samples, no round."""
    if len(samples_muc) < 3:
        raise ValueError(f"price feed needs >= 3 samples, got {len(samples_muc)}")
    for wid, v in samples_muc.items():
        check_int_amount(v, f"sample[{wid}]")
        if v <= 0:
            raise ValueError(f"sample[{wid}] must be positive")
    med = _median(list(samples_muc.values()))
    rnd = PriceRound(day=day, samples_muc=dict(samples_muc), median_muc=med)
    for wid, v in samples_muc.items():
        deviation = abs(v - med) * 10000 // med if med else 0
        if deviation > band_bps:
            rnd.outliers[wid] = deviation
        else:
            rnd.accepted.append(wid)
    return rnd


def erg_to_usds_muc(erg_units: int, price_per_erg_muc: int) -> int:
    """Convert an ERG-denominated quote into µ¢ at the feed price.
    Integer math only; rounding happens once, at the boundary (ADR-0007)."""
    check_int_amount(erg_units, "erg_units")
    if price_per_erg_muc <= 0:
        raise ValueError("feed price must be positive")
    return erg_units * price_per_erg_muc
