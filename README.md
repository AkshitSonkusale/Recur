# Recur

Built for Razorpay AI Buildathon 2026 — Track 03, AI Revenue Recovery.

Detects revenue at risk across three failure shapes (failed UPI Autopay
mandates, abandoned checkouts, overdue B2B receivables), diagnoses each with
a trained ML model, decides the right bounded intervention under real
NPCI-derived compliance rules, executes it (including real calls to
Razorpay's test-mode Payment Links API), and logs a full audit trail. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design writeup and honest
results.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .env.example .env   # optional: add Razorpay TEST-MODE keys to send real
                        # test-mode payment links; leave blank to run in mock mode

python data/generate_data.py   # generates data/historical_data.csv and data/current_batch.csv
python agent/scorer.py          # trains the Detective model, prints held-out AUC/Brier
python run_batch.py             # runs the full agent over the batch, writes reports/

python tests/test_guardrails.py
python tests/test_decision_engine.py
```

Output: `reports/report.md` (human-readable batch summary), `reports/report.json`
(full detail), `reports/audit_trail.jsonl` (per-transaction audit trail),
`reports/training_metrics.json` (model evaluation).

## What "the bar" asks for, and where it's met

| Requirement | Where |
|---|---|
| Measured money recovered across a batch | `run_batch.py` → `reports/report.md`, run over the full 76-transaction batch, no cherry-picking |
| Compliant escalation | `agent/guardrails.py` — real NPCI/UPI Autopay retry-cap, notification-lead-time, and revocation rules |
| Stopping rules | Same file — hard stops on risk-flagged transactions, exhausted retry caps, revoked mandates, negative expected value, contact fatigue |
| Audit trail | `agent/audit.py` → `reports/audit_trail.jsonl`, one full decision trace per transaction |

## Repo layout

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the component breakdown
(Detective / Decision-Maker / Doer / Audit) and the reasoning behind the
"mandate retry sequencer" framing.
