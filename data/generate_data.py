"""Synthetic data generator.

Produces two files:
  data/historical_data.csv  - ~600 RESOLVED cases with a `recovered` outcome
                               label. Used ONLY to train the
                               scorer (agent/scorer.py). Never shown to the
                               decision engine directly.
  data/current_batch.csv    - ~76 unresolved cases with no outcome label.
                               This is what the agent runs on.

current_batch.csv includes edge cases on purpose (mandates at the retry
limit, revoked mandates, risk-flagged rows, rows still inside the
notification window, small invoices already chased several times) so the
rule checks get exercised rather than only the straightforward path.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import schema
from agent.ground_truth import simulate_outcome

RNG = np.random.default_rng(42)

FIRST_NAMES = ["Aarav", "Vivaan", "Ishaan", "Priya", "Ananya", "Diya", "Rohan",
               "Kabir", "Meera", "Sara", "Aditya", "Neha", "Karan", "Riya",
               "Arjun", "Pooja", "Vikram", "Sneha", "Rahul", "Isha"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Gupta", "Nair", "Reddy", "Khan",
              "Mehta", "Joshi", "Kapoor", "Rao", "Singh", "Das", "Pillai"]

MANDATE_AMOUNTS = [99, 199, 299, 499, 999, 1499, 2999]
MANDATE_FAILURE_WEIGHTS = {
    schema.FAILURE_INSUFFICIENT_FUNDS: 0.45,
    schema.FAILURE_DO_NOT_HONOR: 0.20,
    schema.FAILURE_BANK_TIMEOUT: 0.20,
    schema.FAILURE_RISK_BLOCK: 0.15,
}


def _customer():
    name = f"{RNG.choice(FIRST_NAMES)} {RNG.choice(LAST_NAMES)}"
    email = name.lower().replace(" ", ".") + f"{RNG.integers(1, 999)}@example.com"
    contact = "+91" + "".join(str(d) for d in RNG.integers(0, 9, size=10))
    return name, email, contact


def _base_row(case_type: str) -> dict:
    name, email, contact = _customer()
    return {
        "case_type": case_type,
        "customer_name": name,
        "customer_email": email,
        "customer_contact": contact,
        "attempt_count": 0,
        "contact_count": 0,
        "days_overdue": 0,
        "hours_since_notification": 48.0,
        "salary_proximity_days": 0,
        "mandate_revoked": False,
        "promised_to_pay": False,
    }


def gen_mandate_row(force: dict | None = None) -> dict:
    row = _base_row(schema.CASE_MANDATE_FAILURE)
    row["failure_code"] = RNG.choice(
        list(MANDATE_FAILURE_WEIGHTS.keys()), p=list(MANDATE_FAILURE_WEIGHTS.values())
    )
    row["amount"] = float(RNG.choice(MANDATE_AMOUNTS))
    row["attempt_count"] = int(RNG.integers(0, 3))
    row["salary_proximity_days"] = int(RNG.integers(-15, 16))
    row["hours_since_notification"] = float(RNG.integers(24, 96))
    row["mandate_revoked"] = bool(RNG.random() < 0.05)
    if force:
        row.update(force)
    return row


def gen_checkout_row(force: dict | None = None) -> dict:
    row = _base_row(schema.CASE_CHECKOUT_ABANDON)
    row["failure_code"] = schema.FAILURE_CART_ABANDONED
    row["amount"] = float(RNG.integers(100, 8000))
    row["contact_count"] = int(RNG.integers(0, 3))
    if force:
        row.update(force)
    return row


def gen_receivable_row(force: dict | None = None) -> dict:
    row = _base_row(schema.CASE_RECEIVABLE_OVERDUE)
    row["failure_code"] = schema.FAILURE_INVOICE_OVERDUE
    row["amount"] = float(RNG.integers(5000, 500_000))
    row["days_overdue"] = int(RNG.integers(1, 90))
    row["contact_count"] = int(RNG.integers(0, 5))
    row["promised_to_pay"] = bool(RNG.random() < 0.30)
    if force:
        row.update(force)
    return row


def default_action(row: dict) -> str:
    if row["case_type"] == schema.CASE_MANDATE_FAILURE:
        return schema.ACTION_SCHEDULE_RETRY
    if row["case_type"] == schema.CASE_RECEIVABLE_OVERDUE and row["amount"] > schema.RECEIVABLE_HUMAN_ESCALATION_THRESHOLD_INR:
        return schema.ACTION_ESCALATE_HUMAN
    return schema.ACTION_SEND_PAYMENT_LINK


def build_historical(n_each=(250, 200, 150)) -> pd.DataFrame:
    rows = []
    for _ in range(n_each[0]):
        rows.append(gen_mandate_row())
    for _ in range(n_each[1]):
        rows.append(gen_checkout_row())
    for _ in range(n_each[2]):
        rows.append(gen_receivable_row())

    df = pd.DataFrame(rows)
    df["txn_id"] = [f"HIST-{i:04d}" for i in range(len(df))]
    df["recovered"] = [
        simulate_outcome(r, default_action(r), RNG) for r in df.to_dict("records")
    ]
    return df


def build_current_batch() -> pd.DataFrame:
    rows = []

    # --- normal spread -----------------------------------------------------
    for _ in range(24):
        rows.append(gen_mandate_row())
    for _ in range(20):
        rows.append(gen_checkout_row())
    for _ in range(16):
        rows.append(gen_receivable_row())

    # --- deliberate edge cases to exercise the guardrails -------------------
    for _ in range(4):  # NPCI retry cap exhausted -> must escalate, not retry
        rows.append(gen_mandate_row({"attempt_count": schema.MAX_MANDATE_ATTEMPTS,
                                      "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS}))
    for _ in range(3):  # mandate revoked by customer -> hard stop on auto-debit
        rows.append(gen_mandate_row({"mandate_revoked": True,
                                      "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS}))
    for _ in range(3):  # risk-flagged -> must NOT be auto-retried
        rows.append(gen_mandate_row({"failure_code": schema.FAILURE_RISK_BLOCK,
                                      "attempt_count": 0}))
    for _ in range(3):  # pre-debit notification not yet 24h old -> must wait
        rows.append(gen_mandate_row({"hours_since_notification": float(RNG.integers(1, 23)),
                                      "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS}))
    for _ in range(3):  # tiny, heavily-chased overdue invoices -> negative EV
        rows.append(gen_receivable_row({"amount": float(RNG.integers(200, 800)),
                                         "contact_count": 5, "days_overdue": 75}))

    df = pd.DataFrame(rows)
    df["txn_id"] = [f"TXN-{i:04d}" for i in range(len(df))]
    return df.sample(frac=1.0, random_state=7).reset_index(drop=True)  # shuffle


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))

    hist = build_historical()
    hist.to_csv(os.path.join(out_dir, "historical_data.csv"), index=False)
    print(f"Wrote historical_data.csv: {len(hist)} rows, "
          f"{hist['recovered'].mean():.1%} historically recovered")

    batch = build_current_batch()
    batch.to_csv(os.path.join(out_dir, "current_batch.csv"), index=False)
    print(f"Wrote current_batch.csv: {len(batch)} rows across "
          f"{batch['case_type'].value_counts().to_dict()}")
