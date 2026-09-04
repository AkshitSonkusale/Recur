"""Checks on the message layer.

These matter more than the usual unit test, because this is the only part of
the system where a language model produces output. The point of these tests is
that bad model output is caught rather than sent.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import messenger, schema


def _row(**overrides):
    row = {
        "txn_id": "TXN-0001",
        "case_type": schema.CASE_MANDATE_FAILURE,
        "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS,
        "amount": 499.0,
        "customer_name": "Test Customer",
        "mandate_revoked": False,
    }
    row.update(overrides)
    return row


# --- what the checks must reject --------------------------------------------

def test_rejects_threatening_language():
    ok, reason = messenger.validate(
        "Aapka payment of ₹499 pending hai. Pay now or we will take legal action.",
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert not ok and "pressuring" in reason


def test_rejects_credit_score_pressure():
    ok, reason = messenger.validate(
        "Please clear ₹499, it may affect your CIBIL score.",
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert not ok


def test_rejects_wrong_amount():
    ok, reason = messenger.validate(
        "Your payment of ₹4,999 is still pending. Please complete it.",
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert not ok and "wrong amount" in reason


def test_rejects_missing_amount():
    ok, reason = messenger.validate(
        "Your payment is still pending, please complete it soon.",
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert not ok and "amount missing" in reason


def test_rejects_invented_url():
    ok, reason = messenger.validate(
        "Pay ₹499 here: https://totally-not-our-domain.example/pay",
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert not ok and "URL" in reason


def test_rejects_overlong_message():
    ok, reason = messenger.validate(
        "Aapka ₹499 payment pending hai. " + ("bahut lamba message. " * 30),
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert not ok and "too long" in reason


def test_rejects_promising_debit_on_revoked_mandate():
    ok, reason = messenger.validate(
        "Hum aapke account se ₹499 auto-debit karenge kal.",
        _row(mandate_revoked=True), schema.ACTION_ESCALATE_MANUAL_PAYMENT)
    assert not ok and "revoked" in reason


# --- what the checks must allow ---------------------------------------------

def test_accepts_clean_hinglish_message():
    ok, reason = messenger.validate(
        "Aapka ₹499 ka payment abhi pending hai. Jab convenient ho, aap ise complete kar sakte hain.",
        _row(), schema.ACTION_SEND_PAYMENT_LINK)
    assert ok, reason


def test_accepts_revoked_message_that_says_debits_stopped():
    ok, reason = messenger.validate(
        "Hum ₹499 collect nahi kar paaye. Aage koi auto-debit nahi hoga, aap manually pay kar sakte hain.",
        _row(mandate_revoked=True), schema.ACTION_ESCALATE_MANUAL_PAYMENT)
    assert ok, reason


# --- end to end, with the model call faked -----------------------------------

class _FakeResponse:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._text}}]}


def _with_fake_model(text, fn):
    original_post = messenger.requests.post
    os.environ["GROQ_API_KEY"] = "test-key-not-real"
    messenger.requests.post = lambda *a, **kw: _FakeResponse(text)
    try:
        return fn()
    finally:
        messenger.requests.post = original_post
        os.environ.pop("GROQ_API_KEY", None)


def test_bad_model_output_falls_back_to_template():
    msg = _with_fake_model(
        "Pay ₹99999 immediately or we will take legal action.",
        lambda: messenger.compose(_row(), schema.ACTION_SEND_PAYMENT_LINK, "[link]"),
    )
    assert msg.source == "template_after_failed_check"
    assert not msg.checks_passed
    assert "499" in msg.text          # the template carries the real amount
    assert "legal action" not in msg.text


def test_good_model_output_is_used():
    msg = _with_fake_model(
        "Aapka ₹499 ka payment pending hai. Jab time mile, complete kar dijiye.",
        lambda: messenger.compose(_row(), schema.ACTION_SEND_PAYMENT_LINK, "[link]"),
    )
    assert msg.source == "llm"
    assert msg.checks_passed
    assert msg.text.endswith("[link]")   # link appended by us, not written by the model


def test_no_message_when_agent_stands_down():
    assert messenger.compose(_row(), schema.ACTION_DO_NOTHING, None) is None


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
