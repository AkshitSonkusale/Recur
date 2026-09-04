"""Doer: executes the chosen recovery action.

`send_payment_link` and `escalate_manual_payment` call Razorpay's real
TEST-MODE Payment Links API (https://api.razorpay.com/v1/payment_links/) when
RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are set in the environment. If they are
not set (or the call fails), execution degrades gracefully to a clearly
logged MOCK result — the pipeline never crashes for lack of credentials.

`schedule_retry` and `escalate_human` don't have a public merchant-triggered
Razorpay API in the same sense (real UPI Autopay retries are bank/NPCI
orchestrated on schedule; internal escalation would hit a support system) —
these are simulated and explicitly logged as such.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from agent import schema

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1/payment_links/"


@dataclass
class ExecutionResult:
    status: str          # "executed_live" | "executed_mock" | "simulated" | "skipped"
    detail: str
    external_ref: str | None = None


def _razorpay_credentials():
    key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
    return key_id, key_secret


def _create_payment_link(row: dict, purpose: str) -> ExecutionResult:
    key_id, key_secret = _razorpay_credentials()
    payload = {
        "amount": int(round(row["amount"] * 100)),  # paise
        "currency": "INR",
        "description": f"{purpose} — {row['case_type']} ({row['failure_code']}) [{row['txn_id']}]",
        "reference_id": row["txn_id"],
        "customer": {
            "name": row["customer_name"],
            "email": row["customer_email"],
            "contact": row["customer_contact"],
        },
        "notify": {"sms": True, "email": True},
        "reminder_enable": True,
        "notes": {"case_type": row["case_type"], "failure_code": row["failure_code"]},
    }

    if not key_id or not key_secret:
        return ExecutionResult(
            "executed_mock",
            f"MOCK (no RAZORPAY_KEY_ID/SECRET set): would create a test-mode payment link "
            f"for ₹{row['amount']:.0f} and notify {row['customer_contact']}.",
            external_ref=f"mock_plink_{row['txn_id']}",
        )

    try:
        resp = requests.post(
            RAZORPAY_BASE_URL, json=payload, auth=(key_id, key_secret), timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return ExecutionResult(
            "executed_live",
            f"Live Razorpay test-mode payment link created: {data.get('short_url')}",
            external_ref=data.get("id"),
        )
    except Exception as exc:  # network error, bad creds, etc. — never crash the batch
        return ExecutionResult(
            "executed_mock",
            f"Razorpay API call failed ({exc}); fell back to MOCK so the batch still completes.",
            external_ref=f"mock_plink_{row['txn_id']}",
        )


def _next_non_peak_window() -> str:
    now = datetime.now(timezone.utc)
    if now.hour in schema.PEAK_HOURS or now.hour < 11:
        target = now.replace(hour=11, minute=0, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return f"{target.isoformat()} (mid-day non-peak window)"
    target = now.replace(hour=23, minute=0, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    return f"{target.isoformat()} (late-night non-peak window)"


def execute(row: dict, action: str) -> ExecutionResult:
    if action == schema.ACTION_SEND_PAYMENT_LINK:
        return _create_payment_link(row, "Payment recovery")

    if action == schema.ACTION_ESCALATE_MANUAL_PAYMENT:
        return _create_payment_link(row, "Manual payment required (auto-debit retries exhausted)")

    if action == schema.ACTION_SCHEDULE_RETRY:
        when = _next_non_peak_window()
        return ExecutionResult(
            "simulated",
            f"Scheduled next UPI Autopay retry for {when}; pre-debit notification will be "
            f"(re)sent >= {schema.NOTIFICATION_LEAD_HOURS}h ahead of the attempt.",
            external_ref=f"retry_sched_{row['txn_id']}",
        )

    if action == schema.ACTION_ESCALATE_HUMAN:
        ticket_id = f"TICKET-{abs(hash(row['txn_id'])) % 100000:05d}"
        return ExecutionResult(
            "simulated",
            f"Opened internal recovery ticket {ticket_id} for a human agent "
            f"(₹{row['amount']:.0f}, {row['case_type']}).",
            external_ref=ticket_id,
        )

    return ExecutionResult("skipped", "No action taken (do_nothing).", external_ref=None)
