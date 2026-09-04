# Difficulties faced while building Recur

Kept honestly and updated as they come up — useful both as a build log and
as source material for the buildathon submission form.

## 1. Avoiding label leakage in the ML scorer

The Detective needs a `recovery_probability` that's actually learned, not a
hardcoded lookup table — but the synthetic data generator "knows" the true
underlying probability it used to create each row, and naively exposing
that to the model would make it trivially, meaninglessly accurate. Solved
by splitting the generating logic into two files that never talk to each
other except through simulated outcomes: `agent/ground_truth.py` (hidden,
only used to *label* historical data and to *simulate* real-world results
after a decision, never fed into training as a feature) and
`agent/scorer.py` (which only ever sees observable features + the
historical `recovered` label, and is evaluated on a held-out 20% split it
never trained on).

## 2. Pricing actions other than the "default" one

The model predicts recovery probability under one default action per case
type (e.g. mandate → retry). But the decision engine needs to compare
*several* candidate actions (retry vs. escalate vs. do nothing) against
each other. Training a separate model per action wasn't worth the
complexity for this batch size, so instead each action carries a known
"channel effectiveness" ratio (`schema.ACTION_EFFECTIVENESS`) and the
model's baseline probability gets rescaled by the ratio between the
candidate action and the default action. This is a simplification — real
effectiveness would need actual A/B data per channel — and it's called out
as such in ARCHITECTURE.md rather than presented as more rigorous than it
is.

## 3. Making "stopping rules" real instead of invented

It would have been easy to invent guardrail thresholds (e.g. "max 3
retries") that sound reasonable but aren't grounded in anything. Instead we
went and found Razorpay's own published UPI Autopay guide to source the
actual NPCI-derived limits (1 original + 3 retries, 24h pre-debit
notification, non-peak execution windows, and the customer's unconditional
right to revoke a mandate) and built the guardrail logic directly off
those, with the source cited in ARCHITECTURE.md. Took longer than making
numbers up, but it's the difference between a guardrail that's decoration
and one that's defensible under questioning.

## 4. Proving compliance actually overrides economics

It's one thing to claim "guardrails beat expected value," another to prove
it. Added an explicit unit test (`tests/test_decision_engine.py::
test_compliance_override_beats_ev`) that hands the decision engine a
risk-flagged transaction with an artificially high probability and a large
amount — a case specifically designed to tempt the EV-optimal path — and
asserts it still gets forced to `escalate_human` instead. Cheap to write,
and it's the single test most likely to actually get checked by a reviewer
skeptical that "guardrails" are just a label.

## 5. Not crashing when Razorpay credentials aren't available

The executor calls Razorpay's real test-mode Payment Links API, but the
pipeline still needs to run end-to-end for anyone without keys configured
(including judges just cloning the repo). Wrapped the API call in a
try/except that falls back to a clearly-labeled mock result on any failure
— missing credentials, network issues, bad response — so the batch always
completes instead of dying partway through.

## 6. Windows console couldn't print/write the ₹ symbol

Ran into this directly while testing on Windows: `UnicodeEncodeError:
'charmap' codec can't encode character '₹'`. Windows terminals
default to a legacy codepage (cp1252) that doesn't include the ₹ symbol,
so both `print()` and plain `open(..., "w")` file writes crashed the
moment a rupee amount hit the console or a report file. Fixed by forcing
UTF-8 explicitly on every file write (`encoding="utf-8"`) and
reconfiguring stdout at startup — now runs identically on Windows, Mac,
and Linux.

<!-- Add new entries below this line as they come up. -->
