"""Orchestrates the full loop: Detective (score) -> Decision-Maker (decide,
guardrail-checked) -> Doer (execute) -> Audit, run over the ENTIRE batch —
no cherry-picking a favorable subset."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import audit, decision_engine, executor, schema, scorer  # noqa: E402
from agent.ground_truth import simulate_outcome  # noqa: E402


def run(batch_csv: str, seed: int = 123) -> dict:
    df = pd.read_csv(batch_csv)
    scored = scorer.score(df)
    rng = np.random.default_rng(seed)

    records = []
    for row in scored.to_dict("records"):
        decision = decision_engine.decide(row)
        execution = executor.execute(row, decision.action)

        recovered = False
        if decision.action != schema.ACTION_DO_NOTHING:
            recovered = simulate_outcome(row, decision.action, rng)

        records.append(audit.build_audit_record(row, decision, execution, recovered))

    audit_path = audit.write_audit_log(records)
    report = summarize(records)
    return {"records": records, "report": report, "audit_log_path": audit_path}


def summarize(records: list) -> dict:
    n = len(records)
    total_at_risk = sum(r["amount"] for r in records)
    total_recovered = sum(r["amount_recovered"] for r in records)
    n_recovered = sum(1 for r in records if r["recovered"])

    action_breakdown: dict = {}
    for r in records:
        action_breakdown[r["action"]] = action_breakdown.get(r["action"], 0) + 1

    by_case_type: dict = {}
    for r in records:
        ct = by_case_type.setdefault(r["case_type"], {"at_risk": 0.0, "recovered": 0.0, "n": 0})
        ct["at_risk"] += r["amount"]
        ct["recovered"] += r["amount_recovered"]
        ct["n"] += 1

    exceptions = [
        {"txn_id": r["txn_id"], "case_type": r["case_type"], "amount": r["amount"],
         "action": r["action"], "decision_basis": r["decision_basis"],
         "reason": ("guardrail/EV stood down (do_nothing)" if r["action"] == schema.ACTION_DO_NOTHING
                    else "action executed but not recovered in this cycle")}
        for r in records if not r["recovered"]
    ]

    return {
        "batch_size": n,
        "total_at_risk_inr": round(total_at_risk, 2),
        "total_recovered_inr": round(total_recovered, 2),
        "recovery_rate": round(total_recovered / total_at_risk, 4) if total_at_risk else 0.0,
        "cases_recovered": n_recovered,
        "cases_not_recovered": n - n_recovered,
        "guardrail_forced_decisions": sum(1 for r in records if r["decision_basis"] == "compliance_override"),
        "action_breakdown": action_breakdown,
        "by_case_type": {k: {**v, "at_risk": round(v["at_risk"], 2), "recovered": round(v["recovered"], 2)}
                          for k, v in by_case_type.items()},
        "exceptions": exceptions,
    }
