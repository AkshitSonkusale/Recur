"""Per-transaction audit trail: detected -> scored -> guardrail-checked ->
decided -> executed -> outcome. Written as JSON Lines so it's both
human-readable and trivially machine-parseable for a dashboard later."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG_PATH = os.path.join(_HERE, "..", "reports", "audit_trail.jsonl")


def build_audit_record(row: dict, decision, execution, recovered: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    steps = [
        {"step": "detected_failure", "at": now, "detail": f"{row['case_type']} / {row['failure_code']}"},
        {"step": "risk_scored", "at": now,
         "detail": f"recovery_probability={row['recovery_probability']:.2f} (ML-scored, see agent/scorer.py)"},
        {"step": "guardrail_checked", "at": now, "detail": " ".join(decision.guardrail_notes)},
        {"step": "decision_made", "at": now, "detail": decision.reasoning},
        {"step": "action_executed", "at": now,
         "detail": f"{decision.action} -> {execution.status}: {execution.detail}"},
        {"step": "outcome_observed", "at": now, "detail": f"recovered={recovered}"},
    ]
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
        "steps": steps,
    }


def write_audit_log(records: list) -> str:
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return AUDIT_LOG_PATH
