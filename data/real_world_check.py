"""Runs the scorer against a real, public repayment dataset.

Why this exists
---------------
The batch the agent runs on is generated (data/generate_data.py), because no
public dataset of failed UPI Autopay mandates exists. That is fine for showing
the decision path end to end, but it means the headline ROC-AUC is measured on
data whose outcome rule I wrote myself. A model can only look good on that.

So this script takes the same feature builder and the same classifier and
points them at 30,000 real customer repayment histories: the UCI "Default of
Credit Card Clients" dataset (Taiwan, 2005). Different country, different
instrument, real outcomes nobody generated. If the signal the scorer leans on
is real, it should survive the move. If it was an artefact of my generator, it
should collapse here.

This is deliberately separate from the main run. It writes only
reports/real_world_metrics.json, trains its own model in memory, and touches
neither agent/model.pkl nor reports/training_metrics.json. Nothing in the
batch, the dashboard or the docs depends on it.

What is NOT claimed
-------------------
This is not a validation of the whole model. Four of the scorer's features
(contact_count, hours_since_notification, salary_proximity_days,
promised_to_pay, mandate_revoked) have no equivalent in a credit-card
repayment table, so they sit at zero here. What this measures is the part that
does transfer: whether outstanding balance, how many billing cycles a customer
has already missed, and how deep the delinquency runs actually predict whether
the next collection succeeds. That is the backbone of the scorer, and it is
the part worth testing against something I did not write.

Protected attributes
--------------------
The dataset ships with SEX, EDUCATION, MARRIAGE and AGE columns. None of them
are used. A collections model that keys off a customer's sex or marital status
is a discrimination problem wearing a ROC curve, and it is not something a
payments company should ship. EXCLUDED_COLUMNS below is enforced, not just
documented: the mapping asserts none of them reach the feature frame.

Usage
-----
    python data/real_world_check.py

Downloads the CSV on first run (about 2.8 MB) into data/external/ and reuses
it afterwards. If your network blocks the download, fetch UCI_Credit_Card.csv
yourself and drop it in data/external/.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import features, schema  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

CSV_PATH = os.path.join(_HERE, "external", "UCI_Credit_Card.csv")
SOURCE_URL = (
    "https://raw.githubusercontent.com/YuChenAmberLu/"
    "Data-Science--Credit-Card-Default/master/UCI_Credit_Card.csv"
)
METRICS_PATH = os.path.join(_ROOT, "reports", "real_world_metrics.json")

# Never used as model inputs. See the module docstring.
EXCLUDED_COLUMNS = ["SEX", "EDUCATION", "MARRIAGE", "AGE"]

# NT$ to INR, roughly. Only affects the scale of the amount feature; it does
# not change the ranking the model learns. Stated as a unit conversion, not as
# a claim about what Indian subscription amounts look like.
NTD_TO_INR = 2.7


def fetch() -> str:
    if os.path.exists(CSV_PATH):
        return CSV_PATH
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    print("Downloading the UCI credit card dataset (about 2.8 MB)...")
    import requests
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()
    with open(CSV_PATH, "wb") as f:
        f.write(resp.content)
    print("Saved to data/external/UCI_Credit_Card.csv")
    return CSV_PATH


def to_recovery_cases(raw: pd.DataFrame) -> pd.DataFrame:
    """Reshapes credit card repayment records into the same shape the agent's
    own rows have.

    The mapping, and why each line is defensible:

    PAY_0 is this customer's repayment status in the most recent month.
      -2 no balance, -1 cleared in full  -> nothing was owed, not a collection
                                            failure, dropped.
       0 revolving credit                -> billed, did not clear. One failed
                                            collection cycle.
      >=1 months of delay                -> that many missed cycles, which is
                                            the direct analogue of consecutive
                                            failed attempts against a mandate.

    BILL_AMT1 is the outstanding balance, which is the amount at risk.

    default.payment.next.month is the real outcome: 1 means they defaulted the
    following month. Inverted, that is exactly the label the scorer predicts,
    "did the next collection succeed", and it was recorded by a bank rather
    than produced by my generator.
    """
    df = raw.copy()

    # Only rows where something was actually owed and not cleared.
    df = df[(df["PAY_0"] >= 0) & (df["BILL_AMT1"] > 0)].reset_index(drop=True)

    delay_months = df["PAY_0"].clip(lower=0).astype(int)

    out = pd.DataFrame()
    out["txn_id"] = ["REAL-%05d" % i for i in df["ID"].astype(int)]
    out["case_type"] = schema.CASE_MANDATE_FAILURE
    out["amount"] = (df["BILL_AMT1"] * NTD_TO_INR).round(2)

    # A customer sitting at PAY_0 = 0 has had one unsuccessful cycle; each
    # further month of delay is another. Capped at the mandate limit, since
    # beyond that the agent would have stopped retrying anyway.
    out["attempt_count"] = (delay_months + 1).clip(upper=schema.MAX_MANDATE_ATTEMPTS)
    out["days_overdue"] = delay_months * 30

    # Not present in this dataset. Left at neutral rather than invented.
    out["contact_count"] = 0
    out["hours_since_notification"] = 0.0
    out["salary_proximity_days"] = 0
    out["mandate_revoked"] = False
    out["promised_to_pay"] = False

    out["failure_code"] = np.where(
        delay_months >= 1,
        schema.FAILURE_INSUFFICIENT_FUNDS,   # payment was due and did not arrive
        schema.FAILURE_DO_NOT_HONOR,         # billed, balance carried, not cleared
    )

    out["recovered"] = df["default.payment.next.month"].astype(int).eq(0)
    return out


def main() -> dict:
    raw = pd.read_csv(fetch())

    leaked = [c for c in EXCLUDED_COLUMNS if c in raw.columns]
    cases = to_recovery_cases(raw)
    assert not any(c in cases.columns for c in EXCLUDED_COLUMNS), \
        "a protected attribute reached the feature frame"

    X = features.build_feature_frame(cases)
    y = cases["recovered"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = GradientBoostingClassifier(random_state=42, n_estimators=150, max_depth=3)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]

    # A model that always predicts the base rate. Anything at or below this is
    # noise dressed up as a probability.
    baseline_brier = float(brier_score_loss(y_test, np.full(len(y_test), y_train.mean())))

    live_features = sorted(
        [(f, float(w)) for f, w in zip(features.FEATURE_COLUMNS, model.feature_importances_)
         if w > 0.001],
        key=lambda kv: -kv[1],
    )

    metrics = {
        "dataset": "UCI Default of Credit Card Clients (Taiwan, 2005), 30000 customers",
        "source_url": SOURCE_URL,
        "rows_in_dataset": int(len(raw)),
        "rows_used_as_failed_collections": int(len(cases)),
        "excluded_protected_columns": leaked,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "base_rate_recovered": float(y.mean()),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "brier_score": float(brier_score_loss(y_test, proba)),
        "brier_score_of_base_rate_guess": baseline_brier,
        "features_with_signal": dict(live_features),
        "features_unavailable_in_this_dataset": [
            "contact_count", "hours_since_notification", "salary_proximity_days",
            "mandate_revoked_flag", "promised_to_pay_flag",
        ],
    }

    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    return metrics


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    m = main()
    print()
    print("Real-world check: UCI Default of Credit Card Clients")
    print(f"  {m['rows_in_dataset']:,} customer records, "
          f"{m['rows_used_as_failed_collections']:,} of them uncleared balances")
    print(f"  Protected columns present and excluded: {', '.join(m['excluded_protected_columns'])}")
    print()
    print(f"  Held-out ROC-AUC : {m['roc_auc']:.3f}")
    print(f"  Brier score      : {m['brier_score']:.4f}  "
          f"(base-rate guess: {m['brier_score_of_base_rate_guess']:.4f})")
    print(f"  Base recovery rate: {m['base_rate_recovered']:.1%}")
    print()
    print("  Features carrying signal here:")
    for name, weight in list(m["features_with_signal"].items())[:6]:
        print(f"    {name:<28} {weight:.3f}")
    print()
    print("  Written to reports/real_world_metrics.json")
