#!/usr/bin/env python3
"""Checks whether the optional API keys actually work.

Neither key is required. Without them the pipeline runs on mocks and
templates. This just tells you which parts are live, so you know whether the
decision log will say `executed_live` or `executed_mock`, and whether messages
will be model-written or templated.

Usage:
    python check_setup.py
"""
from __future__ import annotations

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

from agent import messenger, schema  # noqa: E402


def check_groq() -> bool:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    print("Groq")
    if not key:
        print("  no GROQ_API_KEY set. Messages will use fixed templates.")
        return False

    row = {
        "txn_id": "TXN-CHECK", "case_type": schema.CASE_MANDATE_FAILURE,
        "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS, "amount": 999.0,
        "customer_name": "Test Customer", "mandate_revoked": False,
        "previous_messages": [],
    }
    msg = messenger.compose(row, schema.ACTION_SCHEDULE_RETRY, None)

    if msg.source == "llm":
        print(f"  working, model {messenger.GROQ_MODEL}")
        print(f"  sample: {msg.text}")
        return True
    if msg.source == "template_after_failed_check":
        print(f"  the call worked but the output was rejected: {msg.rejection_reason}")
        print("  that is the checks doing their job. Try again, output varies.")
        return True
    print(f"  not working: {msg.rejection_reason}")
    return False


def check_razorpay() -> bool:
    key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
    print("\nRazorpay")
    if not key_id or not key_secret:
        print("  no RAZORPAY_KEY_ID/SECRET set. Payment links will be mocked.")
        return False

    if not key_id.startswith("rzp_test"):
        print(f"  WARNING: key id is '{key_id[:12]}...', which does not look like a test-mode key.")
        print("  Stopping rather than risking a live call.")
        return False

    try:
        resp = requests.post(
            "https://api.razorpay.com/v1/payment_links/",
            json={
                "amount": 100, "currency": "INR",
                "description": "Recur setup check",
                "customer": {"name": "Test Customer", "email": "test@example.com",
                              "contact": "+919000000000"},
                "notify": {"sms": False, "email": False},
            },
            auth=(key_id, key_secret), timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"  working, test-mode link created: {data.get('short_url')}")
        return True
    except Exception as exc:
        print(f"  not working: {exc}")
        return False


if __name__ == "__main__":
    groq_ok = check_groq()
    razorpay_ok = check_razorpay()

    print("\nSummary")
    print(f"  messages:      {'written by the model' if groq_ok else 'fixed templates'}")
    print(f"  payment links: {'real test-mode API calls' if razorpay_ok else 'mocked'}")
    print("\nEither way `python run_batch.py` works. This only changes how much of it is live.")
