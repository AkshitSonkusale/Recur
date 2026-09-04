"""Hidden ground-truth simulator.

The scorer never imports this. It exists so the demo can label a historical
training set and simulate whether a customer paid after the agent acted, which
is what makes the collected figure a computed number. On real data this module
goes away and actual payment outcomes take its place.
"""
from __future__ import annotations

import numpy as np

from agent import schema


def base_propensity(row) -> float:
    """'True' probability this customer pays if genuinely, properly pursued.
    Deliberately hand-tuned, clearly-labeled assumptions for a synthetic demo —
    not a claim about real Razorpay merchant recovery rates."""
    case = row["case_type"]

    if case == schema.CASE_MANDATE_FAILURE:
        code = row["failure_code"]
        base = {
            schema.FAILURE_DO_NOT_HONOR: 0.10,
            schema.FAILURE_RISK_BLOCK: 0.03,
            schema.FAILURE_BANK_TIMEOUT: 0.65,
            schema.FAILURE_INSUFFICIENT_FUNDS: 0.35,
        }.get(code, 0.20)

        if code == schema.FAILURE_INSUFFICIENT_FUNDS:
            if 0 <= row["salary_proximity_days"] <= 3:
                base += 0.30
            elif -2 <= row["salary_proximity_days"] < 0:
                base += 0.10

        base *= max(0.15, 1 - 0.15 * row["attempt_count"])
        if row["mandate_revoked"]:
            base = 0.0

    elif case == schema.CASE_CHECKOUT_ABANDON:
        base = 0.45
        if row["amount"] < 500:
            base += 0.15
        elif row["amount"] > 5000:
            base -= 0.15
        base -= 0.05 * row["contact_count"]

    elif case == schema.CASE_RECEIVABLE_OVERDUE:
        base = 0.50
        base -= 0.01 * min(row["days_overdue"], 60)
        if row["promised_to_pay"]:
            base += 0.15
        if row["amount"] > 100_000:
            base -= 0.10

    else:
        base = 0.20

    return float(np.clip(base, 0.0, 0.95))


def simulate_outcome(row, action: str, rng: np.random.Generator) -> bool:
    """Simulates whether the customer actually pays, given the propensity
    implied by `base_propensity` and the known effectiveness of `action`.
    `base_propensity` already represents the outcome under each case type's
    DEFAULT_ACTION, so we rescale by the ratio to this action's effectiveness."""
    default_action = schema.DEFAULT_ACTION_FOR_CASE.get(row["case_type"], action)
    if (
        row["case_type"] == schema.CASE_RECEIVABLE_OVERDUE
        and row["amount"] > schema.RECEIVABLE_HUMAN_ESCALATION_THRESHOLD_INR
    ):
        default_action = schema.ACTION_ESCALATE_HUMAN

    default_eff = schema.ACTION_EFFECTIVENESS.get(default_action, 1.0) or 1.0
    action_eff = schema.ACTION_EFFECTIVENESS.get(action, 0.0)

    p = base_propensity(row) * (action_eff / default_eff)
    p = float(np.clip(p, 0.0, 0.97))
    return bool(rng.random() < p)
