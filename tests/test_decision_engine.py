import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import decision_engine, schema


def test_negative_ev_case_stands_down():
    # Tiny amount, low probability -> no candidate should beat do_nothing (net_ev=0)
    row = {
        "txn_id": "T1", "case_type": schema.CASE_RECEIVABLE_OVERDUE,
        "failure_code": schema.FAILURE_INVOICE_OVERDUE, "amount": 50.0,
        "attempt_count": 0, "contact_count": 0, "days_overdue": 80,
        "hours_since_notification": 48.0, "salary_proximity_days": 0,
        "mandate_revoked": False, "promised_to_pay": False,
        "recovery_probability": 0.02,
    }
    d = decision_engine.decide(row)
    assert d.net_ev >= 0  # never chooses a candidate worse than standing down


def test_compliance_override_beats_ev():
    row = {
        "txn_id": "T2", "case_type": schema.CASE_MANDATE_FAILURE,
        "failure_code": schema.FAILURE_RISK_BLOCK, "amount": 50000.0,  # huge $ temptation
        "attempt_count": 0, "contact_count": 0, "days_overdue": 0,
        "hours_since_notification": 48.0, "salary_proximity_days": 0,
        "mandate_revoked": False, "promised_to_pay": False,
        "recovery_probability": 0.9,  # even if "worth it" on paper
    }
    d = decision_engine.decide(row)
    assert d.action == schema.ACTION_ESCALATE_HUMAN
    assert d.decision_basis == "compliance_override"


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
