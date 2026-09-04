"""One record per transaction: what failed, what it scored, which rules
fired, what was decided, what ran, and the outcome. Written as JSON Lines
so it stays readable and is easy to parse for the dashboard."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_HERE, "..", "reports", "decision_log.jsonl")


def build_record(row: dict, decision, execution, recovered: bool, message=None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    steps = [
        {"step": "detected_failure", "at": now, "detail": f"{row['case_type']} / {row['failure_code']}"},
        {"step": "risk_scored", "at": now,
         "detail": f"recovery_probability={row['recovery_probability']:.2f} (model output, see agent/scorer.py)"},
        {"step": "rules_checked", "at": now, "detail": " ".join(decision.guardrail_notes)},
        {"step": "decision_made", "at": now, "detail": decision.reasoning},
        {"step": "action_executed", "at": now,
         "detail": f"{decision.action} -> {execution.status}: {execution.detail}"},
    ]

    if message is not None:
        if message.source == "llm":
            wrote = "Model wrote the message and it passed every check."
        elif message.source == "template_after_failed_check":
            wrote = f"Model output was rejected ({message.rejection_reason}), fixed template sent instead."
        else:
            wrote = f"Fixed template used ({message.rejection_reason})."
        steps.append({"step": "message_written", "at": now,
                      "detail": f"{wrote} Sent to {message.audience}: \"{message.text}\""})

    steps.append({"step": "outcome_observed", "at": now, "detail": f"recovered={recovered}"})

    return {
        "txn_id": row["txn_id"],
        "case_type": row["case_type"],
        "failure_code": row["failure_code"],
        "amount": row["amount"],
        "action": decision.action,
        "decision_basis": decision.decision_basis,
        "probability_used": decision.probability_used,
        "expected_value": decision.expected_value,
        "net_ev": decision.net_ev,
        "execution_status": execution.status,
        "external_ref": execution.external_ref,
        "recovered": recovered,
        "amount_recovered": row["amount"] if recovered else 0.0,
        "candidates_considered": decision.candidates,
        "message_text": message.text if message else None,
        "message_source": message.source if message else None,
        "message_checks_passed": message.checks_passed if message else None,
        "message_rejection_reason": message.rejection_reason if message else None,
        "steps": steps,
    }


def write_log(records: list) -> str:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return LOG_PATH
