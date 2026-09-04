"""Checks whether the optional API keys work. Neither is required."""
import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from agent import messenger, schema

print("Groq")
if not os.environ.get("GROQ_API_KEY", "").strip():
    print("  no key set, messages will use templates")
else:
    row = {"txn_id": "TXN-CHECK", "case_type": schema.CASE_MANDATE_FAILURE,
           "failure_code": schema.FAILURE_INSUFFICIENT_FUNDS, "amount": 999.0,
           "customer_name": "Test Customer", "mandate_revoked": False,
           "previous_messages": []}
    m = messenger.compose(row, schema.ACTION_SCHEDULE_RETRY, None)
    if m.source == "llm":
        print(f"  working, model {messenger.GROQ_MODEL}\n  sample: {m.text}")
    elif m.source == "template_after_failed_check":
        print(f"  call worked, output rejected by the checks: {m.rejection_reason}")
    else:
        print(f"  not working: {m.rejection_reason}")

print("\nRazorpay")
kid = os.environ.get("RAZORPAY_KEY_ID", "").strip()
sec = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
if not kid or not sec:
    print("  no keys set, payment links will be mocked")
elif not kid.startswith("rzp_test"):
    print("  key id does not look like test mode, stopping rather than risking a live call")
else:
    try:
        r = requests.post("https://api.razorpay.com/v1/payment_links/",
            json={"amount": 100, "currency": "INR", "description": "setup check",
                  "customer": {"name": "Test", "email": "t@example.com", "contact": "+919000000000"},
                  "notify": {"sms": False, "email": False}},
            auth=(kid, sec), timeout=15)
        r.raise_for_status()
        print(f"  working, test link: {r.json().get('short_url')}")
    except Exception as e:
        print(f"  not working: {e}")
