"""Rule checks that run before any decision is made.

Two kinds of rule live here. The mandate rules (retry limit, notification
lead time, revocation, risk flags) come from the NPCI constraints listed in
Razorpay's UPI Autopay guide, cited in ARCHITECTURE.md. The contact-frequency
limit on checkout and invoice cases is my own policy choice, and is marked as
such below so the two aren't confused.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent import schema


@dataclass
class GuardrailResult:
    allowed_actions: list          # actions the decision engine may choose from
    forced_action: str | None = None    # if set, compliance overrides EV-optimal choice
    reasons: list = field(default_factory=list)   # human-readable, goes straight into the decision log


def check(row: dict) -> GuardrailResult:
    notes: list[str] = []

    # Nothing is owed any more. Chasing a customer who has already paid is the
    # cheapest mistake to make and the worst one to make twice, so this is
    # checked before anything else.
    if row.get("already_resolved"):
        notes.append("Already collected in an earlier run. Nothing to chase, no contact made.")
        return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)

    if row["case_type"] == schema.CASE_MANDATE_FAILURE:
        # 1. Risk-flagged transactions must never be auto-retried.
        if row["failure_code"] == schema.FAILURE_RISK_BLOCK:
            if row.get("escalations_made", 0) > 0:
                notes.append("Risk-flagged and already with a person from an earlier run. "
                             "No second ticket, no automated contact.")
                return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)
            notes.append("Risk-flagged (failure_code=risk_block). No automated retry. Sent to a "
                         "person for review.")
            return GuardrailResult([schema.ACTION_ESCALATE_HUMAN], schema.ACTION_ESCALATE_HUMAN, notes)

        # 2. Whatever the mandate rules say next, we do not tell the same person
        # to pay manually every single run. Telling someone once is a
        # notification; telling them daily is harassment, and memory is the only
        # reason this is catchable at all.
        if (row["mandate_revoked"] or row["attempt_count"] >= schema.MAX_MANDATE_ATTEMPTS) \
                and row["contact_count"] >= schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE:
            notes.append(f"Manual payment already requested {row['contact_count']} times "
                         f"(limit {schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}). Standing down "
                         "rather than asking again.")
            return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)

        # 3. Mandate revoked by the customer: NPCI/UPI rules give the customer
        #    an unconditional right to pause/revoke, and the merchant cannot
        #    restrict it. No further auto-debit attempts are permitted.
        if row["mandate_revoked"]:
            notes.append("Mandate revoked by the customer. UPI Autopay rules allow no further "
                         "auto-debit attempts, so a manual payment link is offered instead.")
            return GuardrailResult([schema.ACTION_ESCALATE_MANUAL_PAYMENT],
                                    schema.ACTION_ESCALATE_MANUAL_PAYMENT, notes)

        # 4. NPCI retry cap: 1 original attempt + max 3 retries = 4 total.
        if row["attempt_count"] >= schema.MAX_MANDATE_ATTEMPTS:
            notes.append(f"Retry limit reached ({row['attempt_count']}/{schema.MAX_MANDATE_ATTEMPTS}, "
                         "1 original plus 3 retries). No further auto-debit attempts allowed, so "
                         "the customer is asked to pay manually.")
            return GuardrailResult([schema.ACTION_ESCALATE_MANUAL_PAYMENT],
                                    schema.ACTION_ESCALATE_MANUAL_PAYMENT, notes)

        # 5. Mandatory 24h pre-debit notification lead time not yet satisfied.
        if row["hours_since_notification"] < schema.NOTIFICATION_LEAD_HOURS:
            notes.append(f"Notification sent {row['hours_since_notification']:.0f}h ago, needs "
                         f"{schema.NOTIFICATION_LEAD_HOURS}h. Retry waits until the window is met.")
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
            notes.append(f"Contact limit reached ({row['contact_count']}/"
                         f"{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}). No further messages.")
            return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)
        notes.append(f"Contact count {row['contact_count']}/{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}, "
                     "one more message permitted.")
        return GuardrailResult([schema.ACTION_SEND_PAYMENT_LINK, schema.ACTION_DO_NOTHING], None, notes)

    if row["case_type"] == schema.CASE_RECEIVABLE_OVERDUE:
        allowed = [schema.ACTION_DO_NOTHING]
        if row["contact_count"] < schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE:
            allowed.append(schema.ACTION_SEND_PAYMENT_LINK)
            notes.append(f"Automated chaser contact {row['contact_count']}/"
                         f"{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE} permitted.")
        else:
            notes.append(f"Automated contact limit reached ({row['contact_count']}/"
                         f"{schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}). Only human follow-up or "
                         "leaving it remain.")
        if row.get("escalations_made", 0) > 0:
            notes.append("A person is already handling this from an earlier run, so no second "
                         "ticket is opened.")
            if schema.ACTION_SEND_PAYMENT_LINK not in allowed:
                return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING, notes)
        else:
            allowed.append(schema.ACTION_ESCALATE_HUMAN)
        return GuardrailResult(allowed, None, notes)

    return GuardrailResult([schema.ACTION_DO_NOTHING], schema.ACTION_DO_NOTHING,
                            ["Unrecognized case_type, so no action taken."])
