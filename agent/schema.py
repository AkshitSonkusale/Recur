"""Shared constants and enums for Recur.

Keeping these as plain string constants (not a heavier ORM/pydantic model) so the
same vocabulary is trivially shared between the synthetic data generator, the ML
scorer, the decision engine, and the executor.
"""

# --- Case types (map to the buildathon's example directions) -----------------
CASE_MANDATE_FAILURE = "mandate_failure"        # Failed-subscription / Mandate retry sequencer
CASE_CHECKOUT_ABANDON = "checkout_abandonment"   # Checkout drop-off recovery
CASE_RECEIVABLE_OVERDUE = "receivable_overdue"   # B2B receivables chaser / Promise-to-pay tracker

CASE_TYPES = [CASE_MANDATE_FAILURE, CASE_CHECKOUT_ABANDON, CASE_RECEIVABLE_OVERDUE]

# --- Failure / reason codes ---------------------------------------------------
FAILURE_INSUFFICIENT_FUNDS = "insufficient_funds"
FAILURE_BANK_TIMEOUT = "bank_timeout"
FAILURE_DO_NOT_HONOR = "do_not_honor"        # issuer/hard decline - low recovery odds
FAILURE_RISK_BLOCK = "risk_block"            # flagged by risk engine - must NOT be retried
FAILURE_CART_ABANDONED = "cart_abandoned"
FAILURE_INVOICE_OVERDUE = "invoice_overdue"

# --- NPCI / UPI Autopay compliance constants ----------------------------------
# Source: Razorpay's own UPI 2.0 Autopay guide (2026) — "one original attempt plus
# a maximum of three retries", 24h pre-debit notification requirement, and
# non-peak execution windows (avoid the 06:00-11:00 morning-peak failure spike).
MAX_MANDATE_ATTEMPTS = 4          # 1 original + 3 retries
NOTIFICATION_LEAD_HOURS = 24
PEAK_HOURS = set(range(6, 11))     # 06:00-10:59 local time: avoid scheduling retries here
NON_PEAK_WINDOWS = ["11:00-16:00", "23:00-06:00"]

# --- Recovery actions the Doer can take ---------------------------------------
ACTION_SCHEDULE_RETRY = "schedule_retry"                 # mandate: retry within NPCI cap
ACTION_SEND_PAYMENT_LINK = "send_payment_link"            # real Razorpay test-mode API call
ACTION_ESCALATE_MANUAL_PAYMENT = "escalate_manual_payment" # NPCI cap exhausted -> notify customer
ACTION_ESCALATE_HUMAN = "escalate_human"                   # large B2B receivable / repeated broken promise
ACTION_DO_NOTHING = "do_nothing"                            # negative EV or hard-stopped

# --- Approximate per-action operating cost (INR) used in the EV calculation --
# Deliberately rough, clearly-labeled estimates (gateway/SMS/agent-time order of
# magnitude), not a claim of Razorpay's real internal costs.
ACTION_COST_INR = {
    ACTION_SCHEDULE_RETRY: 0.50,
    ACTION_SEND_PAYMENT_LINK: 0.20,
    ACTION_ESCALATE_MANUAL_PAYMENT: 1.00,
    ACTION_ESCALATE_HUMAN: 60.00,
    ACTION_DO_NOTHING: 0.00,
}

# --- Known channel-effectiveness multipliers ----------------------------------
# Treated as a known business constant (analogous to a merchant already knowing
# "SMS nudges convert at ~X% of what a phone call does" from historical A/B
# data) — NOT learned by the ML model. The model instead predicts
# recovery_probability under each case type's DEFAULT_ACTION, and the decision
# engine rescales that baseline by these ratios to price out alternative
# actions (see agent/decision_engine.py).
ACTION_EFFECTIVENESS = {
    ACTION_SCHEDULE_RETRY: 1.00,
    ACTION_SEND_PAYMENT_LINK: 0.80,
    ACTION_ESCALATE_MANUAL_PAYMENT: 0.50,
    ACTION_ESCALATE_HUMAN: 0.65,
    ACTION_DO_NOTHING: 0.00,
}

DEFAULT_ACTION_FOR_CASE = {
    CASE_MANDATE_FAILURE: ACTION_SCHEDULE_RETRY,
    CASE_CHECKOUT_ABANDON: ACTION_SEND_PAYMENT_LINK,
    CASE_RECEIVABLE_OVERDUE: ACTION_SEND_PAYMENT_LINK,  # overridden to ACTION_ESCALATE_HUMAN for large amounts
}
RECEIVABLE_HUMAN_ESCALATION_THRESHOLD_INR = 100_000

# Anti-harassment / contact-fatigue cap for non-mandate channels (checkout
# nudges, receivable chasers). Not an NPCI rule specifically, but the same
# "compliant escalation, stopping rules" principle applied to contact
# frequency generally.
MAX_CONTACT_ATTEMPTS_NON_MANDATE = 3
