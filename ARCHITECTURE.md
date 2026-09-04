# Architecture

Recur handles payments a merchant is owed but hasn't received. Built for the
Razorpay AI Buildathon 2026, Track 03.

## What it covers

Three situations, one pipeline:

1. A UPI Autopay mandate fails when it tries to debit a subscription.
2. A customer leaves checkout without paying.
3. A B2B invoice goes past its due date.

I kept these in one pipeline instead of writing three scripts because the
question is the same each time: is chasing this worth the cost, which method
should I use, and what am I not allowed to do.

## Why mandates are the main case

Recurring payments in India mostly run on UPI Autopay e-mandates, not stored
cards. Razorpay's 2026 Autopay guide lists constraints that come from NPCI
rules:

* One original debit attempt plus a maximum of three retries.
* A notification to the customer at least 24 hours before each attempt,
  carrying the amount, date and mandate reference.
* Retries should stay out of the 06:00-11:00 window where failures spike.
  Mid-day and late night perform better, particularly close to salary
  credit dates.
* A customer can pause or revoke a mandate at any time and the merchant
  cannot block it. Once revoked, no further debit attempts.
* Once the retries are used up, the customer has to be asked to pay
  manually.

The limits in `agent/guardrails.py` come from this list rather than from
thresholds I picked myself, so every number in that file traces back to a
published source (linked at the bottom).

## Pipeline

Each transaction goes through these stages, in order.

**`agent/scorer.py`** trains a GradientBoostingClassifier (scikit-learn) on
`data/historical_data.csv` and evaluates it on a 20% holdout. It returns a
recovery probability per transaction. The probability is what the model
predicts, so it can be checked against the saved evaluation metrics rather
than taken on trust.

**`agent/guardrails.py`** applies the rules above before any decision gets
made. Depending on the transaction it either narrows the list of permitted
actions or fixes one action outright. Cases that get overridden: risk-flagged
transactions (never auto-retried, sent to a person), revoked mandates (no
further debits, manual payment link offered instead), mandates at the
four-attempt limit, and mandates whose 24-hour notice window hasn't elapsed
yet. Checkout and invoice cases get a contact-frequency limit instead, which
is my own policy choice rather than a regulatory one, and is marked as such
in the code.

**`agent/decision_engine.py`** scores every action still permitted:
`expected_value = probability × amount`, minus a per-channel operating cost,
giving a net figure. It takes the highest one. If guardrails fixed an action,
that action is used regardless of the economics, and the record says so. All
candidates are stored, not just the chosen one, so the reason for rejecting
the alternatives is recoverable later.

**`agent/executor.py`** carries out the action. `send_payment_link` and
`escalate_manual_payment` post to Razorpay's test-mode Payment Links API
(`POST /v1/payment_links/`) when `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`
are present, and fall back to a labelled mock otherwise, so the pipeline
completes without credentials. `schedule_retry` and `escalate_human` are
simulated. Real Autopay retries are scheduled by the bank and NPCI rather
than triggered by a single merchant API call, and internal escalation would
go to a support system that doesn't exist here.

**`agent/messenger.py`** writes the message that goes to the customer. This
is the only place a language model is involved, and it runs last on purpose.
By the time it is called, the rules have already decided whether this customer
may be contacted, the decision engine has picked the action, and the executor
has created the link. The model chooses wording and nothing else. It cannot
choose an amount, a channel, a recipient, or whether to make contact.

Whatever it produces is checked before it is used. The checks reject any
rupee figure that is not the real amount, any URL (links come from the
executor, never from the model), threatening or pressuring wording of the kind
that gets collection messages in trouble, anything over 320 characters, and
any message that implies another debit on a mandate the customer has revoked.
A message that fails a check is discarded and a fixed template is sent
instead, with the reason recorded. The same fallback covers a missing API key
or a failed call, so the batch runs either way.

Customer messages are written in Hinglish, which is how these notifications
actually read in India. The pre-debit notice is a good example of why the
model is boxed in: NPCI requires that notice to carry the amount, the timing
and the mandate reference, so those are supplied to it and then verified in
the output rather than trusted.

**`agent/memory.py`** is what the agent remembers between runs, kept in
`reports/memory.json` and keyed by transaction: how many debit attempts it has
made, how many times it has contacted the customer, what it said, whether a
person is already handling it, and whether the money eventually arrived.

This exists because without it the limits are hollow. A four-attempt cap
enforced against a number in a CSV is not the agent counting its own attempts,
it is the agent trusting a field. With memory, the count the rules see is the
count the agent actually caused, and a transaction that has already been paid
stops being chased at all.

Time is simulated on purpose. Rules like the 24-hour notice period only mean
something if time passes between runs, and nobody waits a day between demo
runs, so each run advances a stored clock (24 hours by default,
`--advance-hours` to change it) and every time-based rule is measured against
it. It is labelled as simulated everywhere it appears.

**`agent/logbook.py`** writes one record per transaction to
`reports/decision_log.jsonl`: what failed, what the model scored, which rules
fired, what was decided and why, what was executed, what was said to the
customer and who wrote it, and the result.

`agent/pipeline.py` runs these across the batch and totals it up.
`run_batch.py` is the entry point and writes `reports/report.json` and
`reports/report.md`. `make_dashboard.py` renders `reports/dashboard.html`
from the JSON afterwards.

## Estimating actions the model wasn't trained on

The model predicts recovery under one default action per case type (mandate
goes to retry, checkout and small invoices go to a payment link, large
invoices go to a person). To price a different action, the decision engine
scales that baseline by a channel-effectiveness ratio held in
`schema.ACTION_EFFECTIVENESS`. I treat those ratios as something a merchant
would already know from past channel performance, similar to knowing how an
SMS converts relative to a phone call. They are assumptions, not learned
values, and a production version would fit them from real channel data.

## What repeated runs look like

`python run_batch.py --reset` then `python run_batch.py` twice more, and the
behaviour changes each time because the agent knows what it already did:

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Collected this run | 18 | 8 | 4 |
| Decisions fixed by rules | 20 | 43 | 55 |
| Left alone, already paid | 0 | 18 | 26 |

By run four only one mandate in the whole batch is still eligible for a retry
and 46 of 76 transactions get no action at all. The agent talks less the
longer it runs, which is the correct direction for something chasing people
for money.

`tests/test_memory.py::test_limits_hold_across_ten_runs` runs the rules and
the memory store against each other for ten rounds and asserts that no
transaction exceeds four debit attempts, three customer contacts, or one open
ticket.

## Results from the run in this repo

Reproduce with `python run_batch.py --reset`.

* Model: ROC-AUC 0.69, Brier score 0.19 on a 20% holdout of 600 historical
  cases (480 train, 120 test). Strongest features were amount, days overdue,
  proximity to salary date, and hours since notification. 600 rows is a small
  training set and the AUC reflects that.
* Batch: 76 transactions, ₹37.97L outstanding, ₹8.76L collected, 23.1%.
* 20 decisions were fixed by guardrails instead of by the economics.
* 58 transactions stayed unresolved and are listed individually in
  `reports/report.md`, including ones the agent deliberately left alone
  because the expected value was negative or the contact limit was hit.

Outcome simulation is stochastic, so figures shift slightly between runs.

## What's real and what isn't

Real: the training and evaluation, the rule checks, the decision arithmetic,
the Razorpay test-mode API integration when keys are supplied, the message
generation and its checks, the state carried between runs, and the decision
log.

Simulated: the transaction data, the passage of time between runs, and
whether a customer actually paid after the agent acted. Both come from `agent/ground_truth.py`, which the model
never sees, so the outcome labels can't leak into the features the model
trains on.

## Sources

* Razorpay, "Master Recurring Payments with UPI 2.0 Autopay: 2026 Guide".
  Retry limit, notification requirement, execution windows, revocation.
  https://razorpay.com/blog/master-recurring-payments-upi-autopay-guide/
* Razorpay Docs, "Create a Standard Payment Link". API contract used in
  `agent/executor.py`.
  https://razorpay.com/docs/api/payments/payment-links/create-standard/
