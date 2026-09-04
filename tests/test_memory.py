"""Checks on what the agent remembers between runs.

The last test here is the important one. It runs the rule checks and the
memory store against each other for ten simulated runs and asserts that no
transaction ever goes past its limits. That is the claim the whole project
rests on, so it is worth having a test that would fail loudly if it stopped
being true.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import guardrails, memory, schema


def _fresh_state():
    return {"run_count": 0, "clock_hours": 0.0, "transactions": {}}


def _mandate_row(**overrides):
    row = {
        "txn_id": "TXN-TEST",
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


def test_agent_attempts_add_to_what_came_from_the_csv():
    state = memory.start_run(_fresh_state())
    row = _mandate_row(attempt_count=1)
    memory.record(state, row, schema.ACTION_SCHEDULE_RETRY, False)
    memory.record(state, row, schema.ACTION_SCHEDULE_RETRY, False)
    merged = memory.apply(state, row)
    assert merged["attempt_count"] == 3   # 1 from the file, 2 the agent made


def test_paid_transactions_are_left_alone_afterwards():
    state = memory.start_run(_fresh_state())
    row = _mandate_row()
    memory.record(state, row, schema.ACTION_SCHEDULE_RETRY, True)   # customer paid
    merged = memory.apply(state, row)
    assert merged["already_resolved"] is True
    result = guardrails.check(merged)
    assert result.forced_action == schema.ACTION_DO_NOTHING
    assert "Already collected" in " ".join(result.reasons)


def test_notification_clock_runs_off_the_simulated_clock():
    state = memory.start_run(_fresh_state())
    row = _mandate_row()
    memory.record(state, row, schema.ACTION_SCHEDULE_RETRY, False)  # notice sent at hour 0
    state = memory.start_run(state, advance_hours=6)                 # only 6 hours later
    merged = memory.apply(state, row)
    assert merged["hours_since_notification"] == 6
    assert guardrails.check(merged).forced_action == schema.ACTION_DO_NOTHING  # too soon

    state = memory.start_run(state, advance_hours=20)                # now 26 hours on
    merged = memory.apply(state, row)
    assert merged["hours_since_notification"] == 26
    assert guardrails.check(merged).forced_action is None            # allowed again


def test_previous_messages_are_carried_forward():
    state = memory.start_run(_fresh_state())
    row = _mandate_row()
    memory.record(state, row, schema.ACTION_SEND_PAYMENT_LINK, False, "Aapka payment pending hai.")
    merged = memory.apply(state, row)
    assert merged["previous_messages"] == ["Aapka payment pending hai."]


def test_no_second_ticket_for_the_same_invoice():
    state = memory.start_run(_fresh_state())
    row = {"txn_id": "TXN-INV", "case_type": schema.CASE_RECEIVABLE_OVERDUE,
           "failure_code": schema.FAILURE_INVOICE_OVERDUE, "amount": 250000.0,
           "attempt_count": 0, "contact_count": 3, "hours_since_notification": 0,
           "mandate_revoked": False}
    memory.record(state, row, schema.ACTION_ESCALATE_HUMAN, False)
    merged = memory.apply(state, row)
    result = guardrails.check(merged)
    assert schema.ACTION_ESCALATE_HUMAN not in result.allowed_actions


def test_limits_hold_across_ten_runs():
    """The one that matters. Ten runs of rules and memory against each other,
    asserting nobody gets over-chased."""
    for case in [
        _mandate_row(txn_id="T-A"),
        _mandate_row(txn_id="T-B", mandate_revoked=True),
        _mandate_row(txn_id="T-C", failure_code=schema.FAILURE_RISK_BLOCK),
        {"txn_id": "T-D", "case_type": schema.CASE_CHECKOUT_ABANDON,
         "failure_code": schema.FAILURE_CART_ABANDONED, "amount": 1200.0,
         "attempt_count": 0, "contact_count": 0, "hours_since_notification": 0,
         "mandate_revoked": False},
        {"txn_id": "T-E", "case_type": schema.CASE_RECEIVABLE_OVERDUE,
         "failure_code": schema.FAILURE_INVOICE_OVERDUE, "amount": 90000.0,
         "attempt_count": 0, "contact_count": 0, "hours_since_notification": 0,
         "mandate_revoked": False},
    ]:
        state = _fresh_state()
        for _ in range(10):
            state = memory.start_run(state, advance_hours=24)
            merged = memory.apply(state, case)
            result = guardrails.check(merged)
            action = result.forced_action or result.allowed_actions[0]
            memory.record(state, case, action, False)

        mem = state["transactions"][case["txn_id"]]
        total_attempts = case["attempt_count"] + mem["attempts_made"]
        total_contacts = case["contact_count"] + mem["contacts_made"]

        assert total_attempts <= schema.MAX_MANDATE_ATTEMPTS, \
            f"{case['txn_id']} made {total_attempts} debit attempts"
        assert total_contacts <= schema.MAX_CONTACT_ATTEMPTS_NON_MANDATE, \
            f"{case['txn_id']} contacted the customer {total_contacts} times"
        assert mem["escalations_made"] <= 1, \
            f"{case['txn_id']} opened {mem['escalations_made']} tickets"


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
