"""Writes the message that goes to the customer, once everything else is settled.

The split matters: by the time this module runs, the rule checks have already
decided whether the customer may be contacted at all, the decision engine has
already picked the action, and the executor has already created the payment
link. None of those are the model's to choose. It only writes wording.

Anything it writes is checked before it counts (see `validate`). If a check
fails, or GROQ_API_KEY is missing, or the call errors, the message falls back
to a fixed template and the record says which happened.
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass

import requests

from agent import schema

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Default to a model available on Groq's free tier. The Llama models are
# listed under an enterprise tier and return 404 on a free key. Override with
# GROQ_MODEL in .env; `GET /openai/v1/models` lists what a given key can use.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

MAX_MESSAGE_CHARS = 320

# Wording that must never reach a customer chasing an unpaid amount, whatever
# the model produces. Debt-collection messaging in India is regulated conduct
# and these are the usual ways an automated chaser goes wrong.
BANNED_PATTERNS = [
    r"\blegal action\b", r"\bcourt\b", r"\bpolice\b", r"\blawyer\b", r"\bnotice will be sent\b",
    r"\brecovery agent\b", r"\bblacklist", r"\bcredit score\b", r"\bcibil\b",
    r"\bdefaulter\b", r"\bseiz", r"\bpenalt", r"\bfine\b",
    r"\bimmediately or\b", r"\bfinal warning\b", r"\blast chance\b", r"\bor else\b",
]

CUSTOMER_ACTIONS = {
    schema.ACTION_SEND_PAYMENT_LINK,
    schema.ACTION_ESCALATE_MANUAL_PAYMENT,
    schema.ACTION_SCHEDULE_RETRY,
}


@dataclass
class Message:
    text: str
    audience: str          # "customer" or "internal"
    source: str            # "llm", "template", or "template_after_failed_check"
    checks_passed: bool
    rejection_reason: str | None = None


def mandate_ref(txn_id: str) -> str:
    return "MND-" + txn_id.split("-")[-1]


# --- fixed fallbacks ---------------------------------------------------------

def template_for(row: dict, action: str, link_url: str | None) -> str:
    amount = f"₹{row['amount']:.0f}"
    if action == schema.ACTION_SCHEDULE_RETRY:
        return (f"Reminder: we will try to debit {amount} for your subscription in the next "
                f"24 hours against mandate {mandate_ref(row['txn_id'])}. Please keep your "
                f"balance topped up. You can pause or cancel this mandate anytime in your UPI app.")
    if action == schema.ACTION_ESCALATE_MANUAL_PAYMENT:
        return (f"We could not collect {amount} automatically, so no further auto-debits will "
                f"be attempted. You can pay manually here when convenient: {link_url or '[link]'}")
    if action == schema.ACTION_SEND_PAYMENT_LINK:
        return (f"Your payment of {amount} is still pending. You can complete it here: "
                f"{link_url or '[link]'}")
    return (f"Internal note: {row['txn_id']}, {row['case_type']}, {amount}, "
            f"reason {row['failure_code']}. Needs a person to follow up.")


# --- checks ------------------------------------------------------------------

def validate(text: str, row: dict, action: str) -> tuple[bool, str | None]:
    """Returns (ok, reason_if_not_ok). Deliberately strict: a message that fails
    any of these is discarded rather than patched up."""
    if not text or not text.strip():
        return False, "empty message"

    if len(text) > MAX_MESSAGE_CHARS:
        return False, f"too long ({len(text)} chars, limit {MAX_MESSAGE_CHARS})"

    lowered = text.lower()
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"contains pressuring or threatening wording: {pattern}"

    # The model is never allowed to produce a URL. Links come from the executor.
    if "http" in lowered or "www." in lowered:
        return False, "model produced a URL, links must come from the executor"

    # Every rupee figure in the message must be the real amount. This is the
    # check that catches an invented or altered number.
    expected = round(row["amount"])
    figures = re.findall(r"(?:₹|rs\.?\s*|inr\s*)([0-9][0-9,]*)", lowered)
    if not figures:
        return False, "amount missing from message"
    for fig in figures:
        if int(fig.replace(",", "")) != expected:
            return False, f"wrong amount in message: {fig} instead of {expected}"

    # A revoked mandate must never be told another debit is coming. The
    # negation list has to cover Hinglish as well as English, otherwise a
    # correct message saying "auto-debit nahi hoga" reads as a promise to debit.
    if row.get("mandate_revoked") and re.search(r"\b(debit|auto.?pay|autopay|deduct)", lowered):
        negations = r"\b(no|not|won'?t|will not|stopped|cancelled|canceled|" \
                    r"nahi|nahin|nai|band|bandh|rok|ruk)\b"
        if not re.search(negations, lowered):
            return False, "implies a further debit on a revoked mandate"

    # Don't send someone the same sentence twice. Repetition is what makes an
    # automated chaser feel like a machine that isn't listening.
    for previous in row.get("previous_messages", []):
        if difflib.SequenceMatcher(None, text.lower(), previous.lower()).ratio() > 0.9:
            return False, "too close to a message already sent to this customer"

    return True, None


# --- generation --------------------------------------------------------------

def _prompt(row: dict, action: str, link_url: str | None) -> list:
    amount = f"₹{row['amount']:.0f}"
    audience_rules = (
        "Write in Hinglish, the way Indian fintech apps message customers: mostly English "
        "sentence structure with natural Hindi words mixed in. Keep it warm and factual."
    )

    if action == schema.ACTION_SCHEDULE_RETRY:
        intent = (
            f"Tell the customer we will attempt to debit {amount} for their subscription within "
            f"the next 24 hours against mandate reference {mandate_ref(row['txn_id'])}, ask them "
            f"to keep sufficient balance, and remind them they can pause or cancel the mandate "
            f"anytime from their UPI app. This is a legally required advance notice, so the "
            f"amount, the timing and the mandate reference must all appear."
        )
    elif action == schema.ACTION_ESCALATE_MANUAL_PAYMENT:
        intent = (
            f"Tell the customer we could not collect {amount} automatically and that we will not "
            f"attempt any further automatic debits. Invite them to pay manually whenever it suits "
            f"them. Do not write the link, it gets attached separately."
        )
    elif action == schema.ACTION_SEND_PAYMENT_LINK:
        intent = (
            f"Remind the customer their payment of {amount} is still pending and invite them to "
            f"complete it. Do not write the link, it gets attached separately."
        )
    else:
        audience_rules = "Write a short internal handover note for a support agent, in plain English."
        intent = (
            f"Summarise for a colleague: transaction {row['txn_id']}, {row['case_type']}, {amount}, "
            f"failure reason {row['failure_code']}. Say what needs checking."
        )

    already_said = row.get("previous_messages", [])
    history = ""
    if already_said:
        joined = "\n".join(f"- {m}" for m in already_said[-3:])
        history = (f"\n\nYou have already sent this customer:\n{joined}\n"
                   "Write something different. Do not repeat those sentences.")

    language_rule = (
        "0. Write in Hinglish, not plain English. Hinglish means English sentence structure "
        "with common Hindi words mixed in, written in the Latin alphabet, the way Indian "
        "payment apps actually message people. For example: 'Aapka ₹499 ka payment abhi "
        "pending hai. Jab convenient ho, complete kar dijiye.' Do not write a fully English "
        "message.\n"
        if audience_rules.startswith("Write in Hinglish") else
        "0. Write in plain English.\n"
    )

    system = (
        "You write short payment messages for an Indian payments company. Rules you must follow:\n"
        + language_rule +
        f"1. The only money figure you may write is {amount}. Never any other number with a rupee sign.\n"
        "2. Never threaten, warn, pressure, or mention legal action, credit scores, penalties or deadlines.\n"
        "3. Never write a URL or link.\n"
        # Ask for well under the hard limit. Telling the model the exact limit
        # makes it write right up against it, so ordinary variance tips over
        # and the message gets thrown away for being four characters long.
        f"4. Keep it short, under {MAX_MESSAGE_CHARS - 120} characters. Two sentences is plenty.\n"
        "5. Be polite and factual. No emoji.\n"
        "Reply with the message text only, nothing else."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{audience_rules}\n\n{intent}{history}"},
    ]


def compose(row: dict, action: str, link_url: str | None = None) -> Message | None:
    """Returns the message for this action, or None if the action contacts nobody."""
    if action == schema.ACTION_DO_NOTHING:
        return None

    audience = "customer" if action in CUSTOMER_ACTIONS else "internal"
    fallback = template_for(row, action, link_url)
    api_key = os.environ.get("GROQ_API_KEY", "").strip()

    if not api_key:
        return Message(fallback, audience, "template", True, "no GROQ_API_KEY set")

    # Reasoning models (gpt-oss) think before they answer, and that thinking
    # comes out of the same token budget while being returned in a separate
    # field. Too small a budget and the reasoning eats the whole allowance,
    # leaving no message at all. Give it room, and ask it to think less, since
    # writing a two-line payment reminder does not need deep deliberation.
    payload = {
        "model": GROQ_MODEL,
        "messages": _prompt(row, action, link_url),
        "temperature": 0.4,
        "max_tokens": 4096,
    }
    if "gpt-oss" in GROQ_MODEL:
        payload["reasoning_effort"] = "low"

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 400 and "reasoning_effort" in payload:
            # Some models reject the parameter. Retry once without it.
            payload.pop("reasoning_effort")
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        text = (choice["message"].get("content") or "").strip().strip('"')
        if not text:
            # Almost always means the token budget ran out during reasoning.
            reason = f"model returned no message (finish_reason={choice.get('finish_reason')})"
            return Message(fallback, audience, "template_after_failed_check", False, reason)
    except Exception as exc:
        return Message(fallback, audience, "template", True, f"model call failed: {exc}")

    ok, reason = validate(text, row, action)
    if not ok:
        return Message(fallback, audience, "template_after_failed_check", False, reason)

    if link_url and action in (schema.ACTION_SEND_PAYMENT_LINK,
                                schema.ACTION_ESCALATE_MANUAL_PAYMENT):
        text = f"{text} {link_url}"

    return Message(text, audience, "llm", True, None)
