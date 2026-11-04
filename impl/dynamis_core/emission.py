"""Flow-gated emission (Law 19) — the anti-Steem law, executable.

No emission, incentive, or market may precede a measured business flow. This module
holds the emission splitter and refuses, at the type level, to emit DYN for anything
without a settled, revenue-referenced flow behind it. The invariant it enforces is the
Gate 2.2 acceptance line: `emitted == revenue-verified`, every epoch, no exceptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .canonical import check_id, check_int_amount, split_bps

# genesis#emission_split, in bps — must sum to 10000.
SPLIT_BPS = {
    "verified_work": 4500,
    "evaluation_markets": 1500,
    "compute_providers": 2000,
    "witnesses": 1000,
    "treasury": 1000,
}

# Emission rate: DYN µ-units minted per USDS µ¢ of settled, revenue-verified flow.
# Labeled estimate: the rate is a genesis parameter the owner ratifies (Gate 0.4) and
# the simulator stress-tests (sim/). It is deliberately conservative.
DYN_MU_PER_USDS_MUC = 400


@dataclass
class EmissionLedger:
    """Append-only record of flow-gated emissions. The only constructor of DYN."""
    epoch: int = 1
    cumulative_emitted_dyn_mu: int = 0
    cumulative_revenue_usds_muc: int = 0
    by_channel: dict[str, int] = field(default_factory=dict)
    _flows: list[dict] = field(default_factory=list)

    def record_flow(self, job_id: str, settled_usds_muc: int,
                    state: str, revenue_ref: str, day: int) -> dict | None:
        """Register a settled flow and return its emission split — or None.

        Refuses: unsettled states (Law 19), zero-value flows, duplicate jobs.
        The revenue_ref must exist — a flow without a payer is a self-deal.
        """
        check_id(job_id, "job_id")
        check_id(revenue_ref, "revenue_ref")
        check_int_amount(settled_usds_muc, "settled_usds_muc")
        if any(f["job_id"] == job_id for f in self._flows):
            raise ValueError(f"flow {job_id} already recorded — no double emission")
        if state != "SETTLED":
            raise ValueError(f"Law 19: job {job_id} is {state}, not SETTLED — no emission")
        if settled_usds_muc == 0:
            return None

        mint_mu = settled_usds_muc * DYN_MU_PER_USDS_MUC
        parts = split_bps(mint_mu, [SPLIT_BPS[k] for k in SPLIT_BPS])
        split = dict(zip(SPLIT_BPS, parts))
        for k, v in split.items():
            self.by_channel[k] = self.by_channel.get(k, 0) + v
        self.cumulative_emitted_dyn_mu += mint_mu
        self.cumulative_revenue_usds_muc += settled_usds_muc
        flow = {"job_id": job_id, "day": day, "settled_usds_muc": settled_usds_muc,
                "revenue_ref": revenue_ref, "emitted_dyn_mu": mint_mu, "split": split}
        self._flows.append(flow)
        return flow

    def invariant_holds(self) -> bool:
        """Gate 2.2 line: emitted == revenue-verified, exactly, always."""
        return self.cumulative_emitted_dyn_mu == self.cumulative_revenue_usds_muc * DYN_MU_PER_USDS_MUC

    def flows(self) -> tuple[dict, ...]:
        return tuple(self._flows)


def job_fee_burn_usds(settled_usds_muc: int) -> int:
    """The RC²-accounting burn: each settled job burns a 1% DYN-equivalent slice,
    pointing emission back at usage. Integer µ¢, taken at settle time."""
    return settled_usds_muc // 100
