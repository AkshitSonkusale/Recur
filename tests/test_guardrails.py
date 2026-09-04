import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import guardrails, schema


def _mandate_row(**overrides):
    row = {
        "case_type": schema.CASE_MANDATE_FAILURE,
        "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS,
        "amount": 999.0,
        "attempt_count": 0,
        "contact_count": 0,
        "hours_since_notification": 48.0,
        "mandate_revoked": False,
    }
    row.update(overrides)
    return row


def test_risk_block_forces_human_escalation_not_retry():
    row = _mandate_row(failure_code=schema.FAILURE_RISK_BLOCK)
    result = guardrails.check(row)
    assert result.forced_action == schema.ACTION_ESCALATE_HUMAN
    assert schema.ACTION_SCHEDULE_RETRY not in result.allowed_actions


def test_revoked_mandate_forbids_further_autodebit():
    row = _mandate_row(mandate_revoked=True)
    result = guardrails.check(row)
    assert result.forced_action == schema.ACTION_ESCALATE_MANUAL_PAYMENT
    assert schema.ACTION_SCHEDULE_RETRY not in result.allowed_actions


def test_npci_retry_cap_forces_escalation():
    row = _mandate_row(attempt_count=schema.MAX_MANDATE_ATTEMPTS)
    result = guardrails.check(row)
    assert result.forced_action == schema.ACTION_ESCALATE_MANUAL_PAYMENT


def test_notification_lead_time_defers_not_skips():
    row = _mandate_row(hours_since_notification=5.0)
    result = guardrails.check(row)
    assert result.forced_action == schema.ACTION_DO_NOTHING
    assert "24h" in " ".join(result.reasons) or "notification" in " ".join(result.reasons).lower()


def test_healthy_mandate_allows_retry():
    row = _mandate_row()
    result = guardrails.check(row)
    assert result.forced_action is None
    assert schema.ACTION_SCHEDULE_RETRY in result.allowed_actions


def test_checkout_contact_fatigue_cap():
    row = {"case_type": schema.CASE_CHECKOUT_ABANDON, "contact_count": schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE}
    result = guardrails.check(row)
    assert result.forced_action == schema.ACTION_DO_NOTHING


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
