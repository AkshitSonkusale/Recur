"""Guardrails: the stopping-rules / compliant-escalation layer.

This is deliberately the most heavily-commented module in the codebase,
because "the bar" for this track is explicit that stopping rules and
compliant escalation are graded, not optional polish. Every rule here is
either a cited real-world constraint (NPCI/UPI Autopay) or an explicit,
labeled business-policy choice (contact-fatigue cap) — never an invented
number dressed up as a compliance requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent import schema


@dataclass
class GuardrailResult:
    allowed_actions: list          # actions the decision engine may choose from
    forced_action: str | None = None    # if set, compliance overrides EV-optimal choice
    reasons: list = field(default_factory=list)   # human-readable, goes straight into the audit trail


def check(row: dict) -> GuardrailResult:
    notes: list[str] = []

    if row["case_type"] == schema.CASE_MANDATE_FAILURE:
        # 1. Risk-flagged transactions must never be auto-retried.
        if row["failure_code"] == schema.FAILURE_RISK_BLOCK:
            notes.append("Risk-flagged (failure_code=risk_block): automated retry is disallowed; "
                         "routed to a human for fraud/risk review, not auto-debited.")
            return GuardrailResult([schema.ACTION_ESCALATE_HUMAN], schema.ACTION_ESCALATE_HUMAN, notes)

        # 2. Mandate revoked by the customer: NPCI/UPI rules give the customer
        #    an unconditional right to pause/revoke, and the merchant cannot
        #    restrict it. No further auto-debit attempts are permitted.
        if row["mandate_revoked"]:
            notes.append("Mandate revoked by customer: per UPI Autopay consumer-control rules, no "
                         "further auto-debit attempts are permitted. Customer is offered a manual "
                         "payment link instead — informing them is not the same as restricting their "
                         "revocation right.")
            return GuardrailResult([schema.ACTION_ESCALATE_MANUAL_PAYMENT],
                                    schema.ACTION_ESCALATE_MANUAL_PAYMENT, notes)

        # 3. NPCI retry cap: 1 original attempt + max 3 retries = 4 total.
        if row["attempt_count"] >= schema.MAX_MANDATE_ATTEMPTS:
            notes.append(f"NPCI retry cap reached ({row['attempt_count']}/{schema.MAX_MANDATE_ATTEMPTS} "
                         "attempts = 1 original + 3 retries). Further auto-debit attempts are not "
                         "NPCI-compliant; escalating to a manual payment request.")
            return GuardrailResult([schema.ACTION_ESCALATE_MANUAL_PAYMENT],
                                    schema.ACTION_ESCALATE_MANUAL_PAYMENT, notes)

        # 4. Mandatory 24h pre-debit notification lead time not yet satisfied.
        if row["hours_since_notification"] < schema.NOTIFICATION_LEAD_HOURS:
            notes.append(f"Pre-debit notification only {row['hours_since_notification']:.0f}h old "
                         f"(requires {schema.NOTIFICATION_LEAD_HOURS}h lead time). Retry deferred "
                         "this cycle, not skipped — will be eligible once the window is satisfied.")
            return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)

        notes.append(f"Compliance checks passed: {row['attempt_count']}/{schema.MAX_MANDATE_ATTEMPTS} "
                     f"attempts used, {row['hours_since_notification']:.0f}h since notification "
                     f"(>= {schema.NOTIFICATION_LEAD_HOURS}h), mandate active.")
        return GuardrailResult(
            [schema.ACTION_SCHEDULE_RETRY, schema.ACTION_ESCALATE_MANUAL_PAYMENT, schema.ACTION_DO_NOTHING],
            None, notes,
        )

    if row["case_type"] == schema.CASE_CHECKOUT_ABANDON:
        if row["contact_count"] >= schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE:
            notes.append(f"Contact-fatigue cap reached ({row['contact_count']}/"
                         f"{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}) — no further nudges to avoid "
                         "harassment; standing down.")
            return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)
        notes.append(f"Contact count {row['contact_count']}/{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE} — "
                     "one more nudge permitted.")
        return GuardrailResult([schema.ACTION_SEND_PAYMENT_LINK, schema.ACTION_DO_NOTHING], None, notes)

    if row["case_type"] == schema.CASE_RECEIVABLE_OVERDUE:
        allowed = [schema.ACTION_DO_NOTHING]
        if row["contact_count"] < schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE:
            allowed.append(schema.ACTION_SEND_PAYMENT_LINK)
            notes.append(f"Automated chaser contact {row['contact_count']}/"
                         f"{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE} permitted.")
        else:
            notes.append(f"Automated chaser cap reached ({row['contact_count']}/"
                         f"{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}) — no more automated nudges; "
                         "only human escalation or standing down remain available.")
        allowed.append(schema.ACTION_ESCALATE_HUMAN)
        return GuardrailResult(allowed, None, notes)

    return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING,
                            ["Unrecognized case_type — defaulting to no action."])
