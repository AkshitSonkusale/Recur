# Problems hit while building this

A running list. Added to as things come up.

## Keeping the outcome labels out of the model

The data generator knows the probability it used to create each row. If that
number reached the model as a feature, the model would look accurate and mean
nothing. I split it into two files that only touch each other through
simulated outcomes: `agent/ground_truth.py` generates labels and simulates
what happens after an action, and `agent/scorer.py` only ever sees observable
fields plus the historical `recovered` label, scored on a 20% holdout it never
trained on.

## Comparing actions the model wasn't trained on

The model predicts recovery under one action per case type, but the decision
engine has to compare several (retry, payment link, escalate, leave it). Fitting
a separate model per action wasn't worth it at this data size, so each action
carries a channel-effectiveness ratio in `schema.ACTION_EFFECTIVENESS` and the
baseline gets rescaled by the ratio between the candidate and the default. It's
an approximation. Real numbers would need per-channel conversion data, and I've
said so in ARCHITECTURE.md rather than presenting the ratios as measured.

## Finding the actual rules instead of picking numbers

Easy version: pick "max 3 retries" because it sounds sensible. I went looking
for what UPI Autopay actually permits and found Razorpay's own Autopay guide,
which gives the retry limit, the 24-hour notification requirement, the
execution windows, and the customer's right to revoke. The rule checks are
built off that and the source is linked. Took longer than making numbers up
and it's the part of the project I'd most want to be asked about.

## Checking that the rules actually beat the arithmetic

Claiming rule checks override the economics is easy, so I wrote a test that
tries to break it: `tests/test_decision_engine.py::test_compliance_override_beats_ev`
feeds a risk-flagged transaction with a high probability and a large amount,
the case most likely to tempt the expected-value path, and asserts the action
still comes out as escalate rather than chase. There's also a real example in
the batch, TXN-0017, where the agent spends ₹60 escalating a ₹499 case at 4.8%
odds, a net loss it takes because the row is risk-flagged.

## Running without Razorpay credentials

The executor calls the test-mode Payment Links API, but the batch still has to
run for anyone who clones the repo without keys. The call is wrapped so any
failure (no credentials, network, bad response) returns a mock result marked as
mock, and the run continues instead of dying halfway.

## Windows couldn't print the rupee sign

`UnicodeEncodeError: 'charmap' codec can't encode character '₹'`. Windows
terminals default to cp1252, which has no ₹, so both `print()` and plain
`open(..., "w")` blew up the first time a rupee amount reached the console. Fixed
by setting `encoding="utf-8"` on every file write and reconfiguring stdout at
startup.

## Letting a model write customer messages without letting it near the money

The obvious way to use an LLM here would be to let it decide what to do with
each failed payment. I didn't want that, because the whole point of the rule
layer is that money decisions are deterministic and traceable. So the model
runs last and only writes wording, after the action, the amount and the
recipient are already fixed. Everything it writes is checked before use: the
amount has to match, no invented links, no threatening or pressuring language,
length limit, and nothing that implies a further debit on a revoked mandate. A
failed check throws the text away and sends a template instead, and the log
records that it happened.

## The Hinglish check that rejected correct messages

My own test caught this. The check that stops a revoked-mandate customer being
told another debit is coming looked for English negation only (no, not, won't,
stopped). A perfectly correct Hinglish message saying "aage koi auto-debit
nahi hoga" has no English negation in it, so it got rejected and fell back to
a template. Fixed by adding Hindi negation words (nahi, nahin, band, rok) to
the check. It's a small thing but it's the kind of bug you only find if you
actually test the language you're claiming to support.

## Memory found a bug that a single run could never show

Adding state between runs immediately exposed something the one-shot version
hid completely. A revoked mandate forces the "please pay manually" message,
and with no memory that decision was correct every time it ran. Run it daily
and the same customer gets the same message every single day, forever. Same
with overdue invoices: a fresh ticket opened for the same invoice on every
run. Both are exactly the harassment pattern the contact limit was written to
prevent, and neither was visible until the agent could remember.

Fixed by checking contact history before repeating an escalation, and by
refusing to open a second ticket for something a person is already handling.
`tests/test_memory.py::test_limits_hold_across_ten_runs` now runs ten rounds
and fails if anything gets over-chased. It's the test I'd point at first if
someone asked whether the limits are real.

## Naming collision with another entry

An early version of the component naming overlapped with vocabulary another
entrant was using for the same track. Renamed the modules to describe what they
do (`scorer`, `guardrails`, `decision_engine`, `executor`, `logbook`) so there's
no resemblance.
