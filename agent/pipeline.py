"""Runs score -> rule check -> decide -> execute -> write message -> log
across every row in the batch, carrying state forward between runs."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import (decision_engine, executor, logbook, memory,  # noqa: E402
                    messenger, schema, scorer)
from agent.ground_truth import simulate_outcome  # noqa: E402


def run(batch_csv: str, seed: int = 123, advance_hours: float = 24.0) -> dict:
    df = pd.read_csv(batch_csv)
    scored = scorer.score(df)
    rng = np.random.default_rng(seed)

    state = memory.start_run(memory.load(), advance_hours)

    records = []
    for raw_row in scored.to_dict("records"):
        row = memory.apply(state, raw_row)
        decision = decision_engine.decide(row)
        execution = executor.execute(row, decision.action)

        message = messenger.compose(row, decision.action, execution.link_url)

        recovered = False
        if decision.action != schema.ACTION_DO_NOTHING:
            recovered = simulate_outcome(row, decision.action, rng)

        memory.record(state, row, decision.action, recovered,
                      message.text if message else None)
        records.append(logbook.build_record(row, decision, execution, recovered, message))

    memory_path = memory.save(state)
    log_path = logbook.write_log(records)
    report = summarize(records)
    report["memory"] = memory.summary(state)
    return {"records": records, "report": report,
            "decision_log_path": log_path, "memory_path": memory_path}


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
        "skipped_already_paid": sum(
            1 for r in records
            if any("Already collected" in s["detail"] for s in r["steps"] if s["step"] == "rules_checked")
        ),
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
