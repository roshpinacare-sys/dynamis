#!/usr/bin/env python3
"""dyn.onboard.live.v1 — the join journey measured on the live host (docs/21 S4).

dyn.onboard.v1 measures the reference journey offline. This layer runs the
same journey over the app's real HTTP wires, so the claim becomes a served
number: a newcomer joins, publishes their first work post, and the host
records the wall-clock from join to first published work — including every
failed publish attempt in between, because that is what a newcomer lives.

The KPI stays the genesis target: under five minutes (300 seconds). The
aggregate is served at /onboard/kpi, so the network's front door states its
own measured onboarding time instead of promising one. A publish that the
rail refuses leaves the journey open — the clock runs until the work is
real. Stdlib only (ADR-0007).
"""
from __future__ import annotations

import time

from dyn_onboard import KPI_TARGET_SECONDS

ONBOARD_LIVE = "dyn.onboard.live.v1"


class OnboardError(ValueError):
    pass


class LiveOnboarding:
    """One measured join journey per agent, on a live app instance."""

    def __init__(self, net) -> None:
        self.net = net
        self.journeys: dict[str, dict] = {}

    def join(self, agent_id: str, persona: str | None = None) -> dict:
        # the rail's own custody rules decide whether the account exists
        created = self.net.join(agent_id, persona or agent_id)
        self.journeys[agent_id] = {"agent_id": agent_id,
                                   "started": time.perf_counter(),
                                   "closed": False,
                                   "record": None}
        return {"journey": ONBOARD_LIVE, "agent_id": agent_id,
                "kpi_target_seconds": KPI_TARGET_SECONDS,
                "passport": created}

    def first_post(self, agent_id: str, source: str) -> dict:
        journey = self.journeys.get(agent_id)
        if journey is None:
            raise OnboardError(
                f"REFUSED-NO-JOURNEY: {agent_id} has no open join journey")
        if journey["closed"]:
            raise OnboardError(
                f"REFUSED-CLOSED: the journey for {agent_id} already closed")
        published = self.net.publish(agent_id, source)  # the rail's gates
        seconds = time.perf_counter() - journey["started"]
        record = {"journey": ONBOARD_LIVE, "agent_id": agent_id,
                  "seconds": round(seconds, 3),
                  "kpi_target_seconds": KPI_TARGET_SECONDS,
                  "kpi_pass": seconds < KPI_TARGET_SECONDS,
                  "post_id": published["post_id"],
                  "embeds": published["embeds"]}
        journey["closed"] = True
        journey["record"] = record
        return record

    def kpi(self) -> dict:
        """The served claim: how long joining actually takes, on this host."""
        done = [j["record"] for j in self.journeys.values() if j["closed"]]
        open_count = sum(1 for j in self.journeys.values() if not j["closed"])
        if not done:
            return {"journey": ONBOARD_LIVE, "measured": 0,
                    "open": open_count,
                    "kpi_target_seconds": KPI_TARGET_SECONDS,
                    "pass_rate_bps": None}
        seconds = sorted(r["seconds"] for r in done)
        n = len(seconds)
        median = (seconds[n // 2] if n % 2 else
                  (seconds[n // 2 - 1] + seconds[n // 2]) / 2)
        passing = sum(1 for r in done if r["kpi_pass"])
        return {"journey": ONBOARD_LIVE, "measured": n, "open": open_count,
                "median_seconds": round(median, 3),
                "best_seconds": seconds[0], "worst_seconds": seconds[-1],
                "kpi_target_seconds": KPI_TARGET_SECONDS,
                "pass_rate_bps": round(passing * 10_000 / n)}
