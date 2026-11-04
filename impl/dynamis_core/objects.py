"""DYNAMIS core protocol objects (docs/03-protocol.md §1) with fail-closed validation.

Every object validates at construction. Validation is the schema-enforcement layer
referenced by schemas/*.schema.json — the JSON Schemas describe the wire shape; this
module is the executable half.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .canonical import check_id, check_int_amount

VERIFICATION_CLASSES = ("A", "B", "C", "D", "E")

JOB_STATES = (
    "OPEN",        # spec posted, not funded
    "FUNDED",      # USDS escrowed
    "CLAIMED",     # worker holds the claim
    "DELIVERED",   # claim + artifacts + runner receipt posted
    "VERIFYING",   # attestation ladder run in progress
    "SETTLED",     # escrow released, fees taken, emission proposed
    "REFUNDED",    # deadline or cancel path, escrow returned to budget
    "DISPUTED",    # challenger opened a dispute within the window
)


@dataclass(frozen=True)
class Job:
    job_id: str
    entity_id: str
    spec: dict                 # schema-validated object, never prose
    escrow_usds_muc: int       # µ¢ escrowed on FUND
    deadline_day: int          # protocol day number
    verification_class: str    # A..E, priced by ladder
    revenue_ref: str           # entity budget envelope or external payment ref (Law 19)

    def __post_init__(self) -> None:
        check_id(self.job_id, "job_id")
        check_id(self.entity_id, "entity_id")
        check_id(self.revenue_ref, "revenue_ref")
        if not isinstance(self.spec, dict) or not self.spec:
            raise ValueError("spec must be a non-empty schema-validated object")
        check_int_amount(self.escrow_usds_muc, "escrow_usds_muc")
        check_int_amount(self.deadline_day, "deadline_day", minimum=1)
        if self.verification_class not in VERIFICATION_CLASSES:
            raise ValueError(f"verification_class must be one of {VERIFICATION_CLASSES}")


@dataclass(frozen=True)
class Claim:
    claim_id: str
    job_id: str
    worker_agent: str
    artifact_hashes: tuple[str, ...]   # sha256 of every artifact
    receipt_hash: str                  # runner :3020 receipt, hash-chained
    day: int

    def __post_init__(self) -> None:
        check_id(self.claim_id, "claim_id")
        check_id(self.job_id, "job_id")
        check_id(self.worker_agent, "worker_agent")
        if not self.artifact_hashes:
            raise ValueError("a claim without artifacts is not verifiable (Law 4)")
        for h in self.artifact_hashes:
            if not (isinstance(h, str) and len(h) == 64 and all(c in "0123456789abcdef" for c in h)):
                raise ValueError(f"artifact hash must be sha256 hex: {h!r}")
        if not (isinstance(self.receipt_hash, str) and len(self.receipt_hash) == 64):
            raise ValueError("receipt_hash must be sha256 hex")
        check_int_amount(self.day, "day", minimum=1)


@dataclass(frozen=True)
class Eval:
    eval_id: str
    claim_id: str
    evaluator_agent: str
    verdict: str               # "pass" | "fail"
    confidence_bps: int        # 0..10000 — scored with Brier (brier.py)
    bond_muc: int              # bond posted at eval time (docs/03 §6)

    def __post_init__(self) -> None:
        check_id(self.eval_id, "eval_id")
        check_id(self.claim_id, "claim_id")
        check_id(self.evaluator_agent, "evaluator_agent")
        if self.verdict not in ("pass", "fail"):
            raise ValueError("verdict must be pass|fail")
        check_int_amount(self.confidence_bps, "confidence_bps")
        if self.confidence_bps > 10000:
            raise ValueError("confidence_bps > 10000")
        check_int_amount(self.bond_muc, "bond_muc")


@dataclass(frozen=True)
class AgentPassport:
    agent_id: str
    persona: str                       # display persona, never a root claim (Law 17)
    keyrefs: tuple[str, ...]           # HSM keyrefs only — never key material (Law 3)
    capabilities: tuple[str, ...]      # scoped, time-boxed, revocable (Law 18)
    wallet: str                        # PowerAccount id
    census_day: int                    # day the custody census last judged this agent

    def __post_init__(self) -> None:
        check_id(self.agent_id, "agent_id")
        if not isinstance(self.persona, str) or not self.persona:
            raise ValueError("persona required")
        if not self.keyrefs:
            raise ValueError("an agent without a keyref cannot sign value (Law 3)")
        for k in self.keyrefs:
            if not (isinstance(k, str) and k.startswith("hsm:")):
                raise ValueError(f"keyref must be an HSM reference, got {k!r}")
        if not self.capabilities:
            raise ValueError("an agent ships with zero capabilities until scoped (Law 18)")
        check_id(self.wallet, "wallet")
        check_int_amount(self.census_day, "census_day", minimum=1)


@dataclass
class PowerAccount:
    account_id: str
    stake_dyn_mu: int = 0            # DYN µ-units staked
    power_points: int = 0
    erg_credits: int = 0             # RC² balance, integer ERG-micro units (rc2.py)
    rc2_cap_erg_mu: int = 0          # accrual cap, grows with stake (rc2.py)
    reputation: dict = field(default_factory=dict)  # ladder grades, brier history

    def __post_init__(self) -> None:
        check_id(self.account_id, "account_id")
        check_int_amount(self.stake_dyn_mu, "stake_dyn_mu")
        check_int_amount(self.erg_credits, "erg_credits")
