"""Shared feature engineering for the Detective's ML scorer.

Used identically at training time (on historical_data.csv, which has a
`recovered` outcome label) and at inference time (on current_batch.csv, which
does not) so the two never drift apart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from agent import schema

FAILURE_CODES = [
    schema.FAILURE_INSUFFICIENT_FUNDS,
    schema.FAILURE_BANK_TIMEOUT,
    schema.FAILURE_DO_NOT_HONOR,
    schema.FAILURE_RISK_BLOCK,
    schema.FAILURE_CART_ABANDONED,
    schema.FAILURE_INVOICE_OVERDUE,
]

NUMERIC_COLS = [
    "amount",
    "attempt_count",
    "contact_count",
    "days_overdue",
    "hours_since_notification",
    "salary_proximity_days",
    "mandate_revoked_flag",
    "promised_to_pay_flag",
]

FEATURE_COLUMNS = NUMERIC_COLS + [f"case_{c}" for c in schema.CASE_TYPES] + [
    f"reason_{f}" for f in FAILURE_CODES
]


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a numeric feature DataFrame with a fixed, stable column set."""
    out = pd.DataFrame(index=df.index)

    out["amount"] = df["amount"].astype(float)
    out["attempt_count"] = df["attempt_count"].astype(float)
    out["contact_count"] = df["contact_count"].astype(float)
    out["days_overdue"] = df["days_overdue"].astype(float)
    out["hours_since_notification"] = df["hours_since_notification"].astype(float)
    out["salary_proximity_days"] = df["salary_proximity_days"].astype(float)
    out["mandate_revoked_flag"] = df["mandate_revoked"].astype(bool).astype(float)
    out["promised_to_pay_flag"] = df["promised_to_pay"].astype(bool).astype(float)

    for c in schema.CASE_TYPES:
        out[f"case_{c}"] = (df["case_type"] == c).astype(float)
    for f in FAILURE_CODES:
        out[f"reason_{f}"] = (df["failure_code"] == f).astype(float)

    # Guarantee stable column order regardless of what categories were present.
    return out.reindex(columns=FEATURE_COLUMNS, fill_value=0.0)
