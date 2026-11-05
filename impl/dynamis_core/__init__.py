"""dynamis_core — executable reference of the DYNAMIS protocol loops.

Stdlib-only by decision (ADR-0007: the reference must run anywhere the fleet runs,
with zero dependency risk). Modules map one-to-one to protocol sections in
docs/03-protocol.md; tests in ../tests/ are the executable acceptance checks.
"""
from .canonical import canon, domain_hash, object_hash, sha256_hex, split_bps, usds
from .escrow import EscrowError, JobMachine, TRANSITIONS
from .objects import AgentPassport, Claim, Eval, Job, PowerAccount
from .policy import Decision, evaluate, TreasuryState, BudgetEnvelope
from .ladder import (CLASSES, ORDER, DEFAULT_BOND_CAP_MUC, floor_class, law9_check,
                     price_verification, sample_for_reexecution)
from .pricefeed import collect_round, erg_to_usds_muc
from .rc2 import accrue, spend, stake_factor
from .brier import brier_score, eval_payout, expected_calibration_error
from .antiherd import mulberry32, schedule_account, least_supported
from .emission import EmissionLedger, SPLIT_BPS

__all__ = [
    "canon", "domain_hash", "object_hash", "sha256_hex", "split_bps", "usds",
    "EscrowError", "JobMachine", "TRANSITIONS",
    "AgentPassport", "Claim", "Eval", "Job", "PowerAccount",
    "Decision", "evaluate", "TreasuryState", "BudgetEnvelope",
    "CLASSES", "ORDER", "DEFAULT_BOND_CAP_MUC", "floor_class", "law9_check",
    "price_verification", "sample_for_reexecution",
    "collect_round", "erg_to_usds_muc", "accrue", "spend", "stake_factor",
    "brier_score", "eval_payout", "expected_calibration_error",
    "mulberry32", "schedule_account", "least_supported",
    "EmissionLedger", "SPLIT_BPS",
]
