"""Decision-Maker: turns a diagnosed probability into a bounded action.

For every candidate action still allowed after guardrails.check(), this
computes expected_value = probability * amount, subtracts a labeled
operating cost, and picks the highest net-EV action — UNLESS a guardrail
forces a specific action regardless of EV (compliance always wins over
economics). Every candidate considered, not just the winner, is kept for the
audit trail so "why this action, and not that one" is answerable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent import guardrails, schema


def estimate_probability(row: dict, action: str) -> float:
    if action == schema.ACTION_DO_NOTHING:
        return 0.0

    default_action = schema.DEFAULT_ACTION_FOR_CASE.get(row["case_type"], action)
    if (row["case_type"] == schema.CASE_RECEIVABLE_OVERDUE
            and row["amount"] > schema.RECEIVABLE_HUMAN_ESCALATION_THRESHOLD_INR):
        default_action = schema.ACTION_ESCALATE_HUMAN

    default_eff = schema.ACTION_EFFECTIVENESS.get(default_action, 1.0) or 1.0
    action_eff = schema.ACTION_EFFECTIVENESS.get(action, 0.0)

    p = float(row["recovery_probability"]) * (action_eff / default_eff)
    return max(0.0, min(p, 0.97))


@dataclass
class DecisionResult:
    txn_id: str
    action: str
    probability_used: float
    expected_value: float
    cost: float
    net_ev: float
    decision_basis: str            # "expected_value" or "compliance_override"
    guardrail_notes: list
    candidates: list = field(default_factory=list)
    reasoning: str = ""


def decide(row: dict) -> DecisionResult:
    gr = guardrails.check(row)

    scored = []
    for action in gr.allowed_actions:
        p = estimate_probability(row, action)
        ev = p * row["amount"]
        cost = schema.ACTION_COST_INR[action]
        net_ev = ev - cost
        scored.append({"action": action, "probability": round(p, 4),
                        "expected_value": round(ev, 2), "cost": cost,
                        "net_ev": round(net_ev, 2)})

    if gr.forced_action:
        chosen = next(s for s in scored if s["action"] == gr.forced_action)
        basis = "compliance_override"
    else:
        chosen = max(scored, key=lambda s: s["net_ev"])
        basis = "expected_value"

    others = ", ".join(
        f"{s['action']}(net_ev=₹{s['net_ev']:.0f})" for s in scored if s is not chosen
    ) or "none"

    reasoning = (
        f"recovery_probability={row['recovery_probability']:.2f} for a ₹{row['amount']:.0f} "
        f"{row['case_type']} case (reason: {row['failure_code']}). "
        f"Guardrails: {' '.join(gr.reasons)} "
        f"Chosen action '{chosen['action']}' "
        + (f"(compliance-forced, overriding economics)."
           if basis == "compliance_override"
           else f"because it has the best net expected value "
                f"(₹{chosen['net_ev']:.0f}) among candidates [{others}].")
    )

    return DecisionResult(
        txn_id=row["txn_id"], action=chosen["action"],
        probability_used=chosen["probability"], expected_value=chosen["expected_value"],
        cost=chosen["cost"], net_ev=chosen["net_ev"], decision_basis=basis,
        guardrail_notes=gr.reasons, candidates=scored, reasoning=reasoning,
    )
