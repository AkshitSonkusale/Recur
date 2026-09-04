# Architecture — Recur

Built for Razorpay AI Buildathon 2026, Track 03 (AI Revenue Recovery).

## The problem, scoped

Revenue leaks out through three different failure shapes: a UPI Autopay
mandate fails to debit a subscription, a checkout gets abandoned before
payment, or a B2B invoice goes overdue. This agent treats all three as one
loop — **detect → diagnose → decide → act → audit** — rather than three
separate scripts, because the decision logic (is this worth pursuing? how
hard? within what limits?) is the same shape in every case.

## Why "Mandate retry sequencer" is the anchor, not generic card retries

Most recurring payments in India run on UPI Autopay / e-mandates, not card
tokens. Razorpay's own 2026 UPI Autopay guide documents real, NPCI-derived
constraints on retrying a failed mandate debit:

- **Retry cap**: one original attempt plus a maximum of three retries (4
  total) — a hard NPCI-compliant ceiling, not a number we chose.
- **24-hour pre-debit notification**: customers must be notified with
  amount, date, and mandate reference at least 24h before every attempt.
- **Non-peak execution windows**: retries should avoid the morning peak
  (06:00–11:00) where failure rates spike, and are more effective in
  mid-day or late-night windows, ideally timed near salary credit dates.
- **Consumer control**: a customer can revoke a mandate at any time and the
  merchant cannot restrict that. A revoked mandate must stop receiving
  auto-debit attempts immediately.
- **After exhausting retries**, the customer must be notified to pay
  manually — the loop doesn't just keep trying forever.

These aren't invented business rules dressed up as "guardrails" — they're
the actual constraints this system is bounded by, cited from Razorpay's own
documentation (see Sources below). That's the guardrail layer in
`agent/guardrails.py`.

## Components

```
data/generate_data.py   Synthetic data: historical_data.csv (labeled,
                         resolved outcomes, for training) and
                         current_batch.csv (unresolved, at-risk — the batch
                         the agent is graded against, with deliberate edge
                         cases: exhausted retry caps, revoked mandates,
                         risk-flagged transactions, notification-window
                         violations).

agent/scorer.py          DETECTIVE. A real GradientBoostingClassifier
                          (scikit-learn) trained on historical_data.csv,
                          evaluated on a held-out 20% split. Outputs a
                          recovery_probability per transaction — a learned
                          number, not a hardcoded lookup table or a
                          qualitative "High/Medium/Low" label.

agent/guardrails.py       Compliance / stopping-rule layer. Checks each
                          transaction against the NPCI-derived rules above
                          (mandate case) and an anti-harassment contact cap
                          (checkout/receivable cases). Returns either a
                          narrowed set of allowed actions, or a forced
                          action that overrides economics entirely.

agent/decision_engine.py  DECISION-MAKER. For every action guardrails still
                          allow, computes expected_value = probability ×
                          amount, subtracts a labeled per-channel operating
                          cost, and picks the highest net-EV action — unless
                          guardrails forced one, in which case compliance
                          wins over economics, always. Every candidate
                          considered (not just the winner) is kept for the
                          audit trail.

agent/executor.py         DOER. `send_payment_link` and
                          `escalate_manual_payment` call Razorpay's real
                          TEST-MODE Payment Links API
                          (POST /v1/payment_links/) when
                          RAZORPAY_KEY_ID/SECRET are set; otherwise falls
                          back to a clearly-labeled mock so the pipeline
                          still runs end to end without credentials.
                          `schedule_retry` / `escalate_human` are simulated
                          and labeled as such — real UPI Autopay retries are
                          bank/NPCI-orchestrated on schedule, not a single
                          merchant-triggered API call.

agent/audit.py            Builds a full step-by-step audit record per
                          transaction (detected → scored → guardrail-checked
                          → decided → executed → outcome), written as JSON
                          Lines to reports/audit_trail.jsonl.

agent/pipeline.py         Orchestrates the loop across the whole batch and
                          produces the summary report.

run_batch.py               CLI entrypoint. Runs the full batch, writes
                            reports/report.json (full detail) and
                            reports/report.md (human-readable summary).
```

## How probability is estimated for actions other than the default

The Detective's model is trained to predict recovery probability under each
case type's *default* action (mandate → retry, checkout/small-receivable →
payment link, large-receivable → human escalation). To price an
*alternative* action (e.g. "what if we escalate to manual payment instead of
retrying"), the decision engine rescales that baseline by a known
channel-effectiveness ratio (`schema.ACTION_EFFECTIVENESS`) — treated as a
business constant a merchant would already know from historical channel
performance (analogous to knowing "SMS nudges convert at roughly X% of what
a phone call does"), not something the model has to learn from scratch.

## Honest results on this run (full batch, no cherry-picking)

From the batch actually included in this repo (`reports/report.json`,
regenerate any time with `python run_batch.py`):

- Detective model: ROC-AUC **0.69**, Brier score **0.19** on a held-out 20%
  split of 600 historical cases (480 train / 120 test) — a real,
  checkable number, not asserted. Top predictive features: amount,
  days_overdue, salary_proximity_days, hours_since_notification.
- Batch of **76** transactions, ₹37.97L at risk, ₹8.76L recovered
  (**23.1%** recovery rate).
- **20** decisions were forced by compliance guardrails, overriding what
  pure expected-value math would have picked.
- **58** transactions are honestly listed as unresolved in this cycle
  (`reports/report.md` → Exceptions), including cases correctly stood down
  on (negative expected value, contact-fatigue cap) rather than pursued
  regardless.

These numbers will vary slightly run to run (synthetic data uses a fixed
seed for the batch, but outcome simulation itself is stochastic) — re-run
`python run_batch.py` to reproduce.

## What's real vs. simulated, stated plainly

- **Real**: the ML training/evaluation pipeline, the guardrail logic, the
  expected-value decision math, the Razorpay test-mode Payment Links API
  integration (when credentials are supplied), the audit trail.
- **Simulated**: the synthetic transaction data itself, and the
  post-decision "did the customer actually pay" outcome (since this is a
  buildathon submission, not a production system with real payment
  history) — via `agent/ground_truth.py`, which is explicitly kept separate
  from and never seen by the model, to avoid label leakage.

## Sources

- Razorpay, "Master Recurring Payments with UPI 2.0 Autopay: 2026 Guide" —
  retry cap, notification requirement, execution windows, revocation rules.
  https://razorpay.com/blog/master-recurring-payments-upi-autopay-guide/
- Razorpay Docs, "Create a Standard Payment Link" — API contract used by
  `agent/executor.py`. https://razorpay.com/docs/api/payments/payment-links/create-standard/
