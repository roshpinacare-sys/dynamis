"""The Delegation-of-Authority policy engine (docs/02 §1, Law 20).

A kernel extension in spirit — deny-by-default, fail-closed, exactly like the estate's
G28 routing policy. The engine classifies an action into a DoA class, checks budget
envelopes and rail caps, and returns what kind of human signature (if any) is required.
Unknown kinds are DENIED, never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .canonical import usds

# Canonical thresholds — mirrors params/genesis.yaml#treasury_policy.doa_classes.
# Amounts are USDS µ¢ (integer); usds() is the only sanctioned dollar literal.
T2_THRESHOLD_MUC = usds(2_000)           # spend > $2,000 is capital
RAIL_MAX_SINGLE_MUC = usds(25_000)       # max_single_flow_usds: 25000
RAIL_MAX_DAILY_MUC = usds(50_000)        # max_daily_usds: 50000
MIN_RUNWAY_MONTHS = 6                    # treasury_policy.min_runway_months

CLASSES = ("T0", "T1", "T2", "T3", "X")

# Action kinds the engine knows. Anything else is denied (fail-closed).
_KINDS = {
    "pay_vendor_bill": "T0",
    "buy_api_credits": "T0",
    "sign_vendor_contract": "T1",
    "post_job_escrow": "T1",
    "pay_agent_salary": "T1",
    "spend_capital": "T2",
    "hire_with_pay": "T2",
    "change_doa": "T3",
    "change_charter": "T3",
    "instantiate_entity": "T3",
    "custody_client_keys": "X",
    "yield_marketing": "X",
    "publish_unmeasured_claim": "X",
}


@dataclass
class BudgetEnvelope:
    name: str
    cap_muc: int
    period: str                      # "monthly" | "weekly"
    spent_muc: int = 0

    def remaining_muc(self) -> int:
        return self.cap_muc - self.spent_muc


@dataclass
class TreasuryState:
    """What the policy engine sees of an entity's books — integers only."""
    envelopes: dict[str, BudgetEnvelope] = field(default_factory=dict)
    daily_spent_muc: int = 0         # today's committed outflow, all envelopes
    runway_months: float = 99.0      # measured, from the entity book (finance spine)

    def book_spend(self, envelope: str, amount_muc: int) -> None:
        env = self.envelopes[envelope]
        env.spent_muc += amount_muc
        self.daily_spent_muc += amount_muc


@dataclass(frozen=True)
class Decision:
    allowed: bool
    doa_class: str
    requires: str                    # none | notify | human_approval | veto_keys | never
    reason: str

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "class": self.doa_class,
                "requires": self.requires, "reason": self.reason}


def classify(kind: str, amount_muc: int) -> str:
    """Class of an action. Amount can push a routine kind up to T2; never down."""
    if kind not in _KINDS:
        return "X"  # unknown = forbidden, fail-closed
    base = _KINDS[kind]
    if base in ("T0", "T1") and amount_muc > T2_THRESHOLD_MUC:
        return "T2"
    return base


def evaluate(state: TreasuryState, kind: str, amount_muc: int,
             envelope: str = "ops", human_approved: bool = False,
             veto_keys: bool = False) -> Decision:
    """The single entry point. Deny is the default answer to everything."""
    if not isinstance(amount_muc, int) or isinstance(amount_muc, bool) or amount_muc < 0:
        return Decision(False, "X", "never", "amount must be a non-negative integer µ¢")

    cls = classify(kind, amount_muc)

    if cls == "X":
        return Decision(False, "X", "never", f"kind {kind!r} is class X — never, by law")

    # Rail caps (G28 pattern: fail-closed caps, no exceptions inside the engine).
    if amount_muc > RAIL_MAX_SINGLE_MUC:
        return Decision(False, cls, "never", "rail cap: single flow above max_single_flow")
    if state.daily_spent_muc + amount_muc > RAIL_MAX_DAILY_MUC:
        return Decision(False, cls, "never", "rail cap: daily outflow above max_daily")

    # Runway floor: any breach is T2 regardless of amount (canon, docs/02 §4).
    if state.runway_months < MIN_RUNWAY_MONTHS:
        cls = "T2"

    # Envelope check — the hard budget law.
    env = state.envelopes.get(envelope)
    if env is None:
        return Decision(False, cls, "never", f"unknown envelope {envelope!r}")
    if amount_muc > env.remaining_muc():
        return Decision(False, cls, "never",
                        f"envelope {envelope} exhausted: "
                        f"{env.remaining_muc()} µ¢ remaining < {amount_muc} µ¢")

    if cls == "T3":
        if not veto_keys:
            return Decision(False, "T3", "veto_keys", "constitutional action needs regulator veto keys")
        return Decision(True, "T3", "veto_keys", "regulator veto keys presented")
    if cls == "T2":
        if not human_approved:
            return Decision(False, "T2", "human_approval",
                            "capital action: agents prepare, the regulator approves")
        return Decision(True, "T2", "human_approval", "regulator approval recorded")

    # T0/T1 pass inside their envelope; T1 additionally commits to notify.
    requires = "none" if cls == "T0" else "notify"
    return Decision(True, cls, requires, "within envelope and rail caps")
