"""Checks on the mapping from the public credit card dataset onto the agent's
own row shape.

The mapping is the part of the real-world check that could quietly be wrong,
because a bad mapping still produces a plausible-looking AUC. These tests run
on a hand-written frame rather than the downloaded CSV, so they work offline.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import features, schema  # noqa: E402
from data.real_world_check import EXCLUDED_COLUMNS, to_recovery_cases  # noqa: E402


def _raw():
    """Four customers covering the cases the mapping has to separate."""
    return pd.DataFrame({
        "ID": [1, 2, 3, 4],
        "SEX": [1, 2, 1, 2],
        "EDUCATION": [1, 2, 3, 1],
        "MARRIAGE": [1, 2, 1, 2],
        "AGE": [24, 41, 33, 58],
        "PAY_0": [-1, 0, 2, 8],          # cleared / revolving / 2 late / 8 late
        "BILL_AMT1": [5000, 12000, 30000, 90000],
        "default.payment.next.month": [0, 0, 1, 1],
    })


def test_protected_attributes_never_reach_the_features():
    cases = to_recovery_cases(_raw())
    for col in EXCLUDED_COLUMNS:
        assert col not in cases.columns
    frame = features.build_feature_frame(cases)
    for col in EXCLUDED_COLUMNS:
        assert col not in frame.columns
    assert list(frame.columns) == features.FEATURE_COLUMNS


def test_customers_who_cleared_their_balance_are_not_collection_failures():
    cases = to_recovery_cases(_raw())
    # Customer 1 paid in full, so there was nothing to collect.
    assert "REAL-00001" not in set(cases["txn_id"])
    assert len(cases) == 3


def test_label_is_the_inverse_of_defaulting_next_month():
    cases = to_recovery_cases(_raw()).set_index("txn_id")
    assert cases.loc["REAL-00002", "recovered"]        # did not default
    assert not cases.loc["REAL-00003", "recovered"]    # defaulted


def test_missed_cycles_are_capped_at_the_mandate_limit():
    cases = to_recovery_cases(_raw()).set_index("txn_id")
    # Eight months late would be nine attempts uncapped; the agent would have
    # stopped long before that, so the feature must not run away.
    assert cases.loc["REAL-00004", "attempt_count"] == schema.MAX_MANDATE_ATTEMPTS
    assert cases.loc["REAL-00002", "attempt_count"] == 1


def test_unavailable_fields_are_neutral_rather_than_invented():
    cases = to_recovery_cases(_raw())
    assert (cases["contact_count"] == 0).all()
    assert (cases["hours_since_notification"] == 0.0).all()
    assert (~cases["mandate_revoked"]).all()
    assert (~cases["promised_to_pay"]).all()


if __name__ == "__main__":
    import inspect
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(failures)
