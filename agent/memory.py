"""What the agent remembers between runs.

Without this, the retry limit and contact limit are enforced against numbers
that arrived in a CSV, not against anything the agent itself did. That is a
real hole: an agent that claims to respect a four-attempt cap should be
counting its own attempts. This module keeps that count.

State lives in reports/memory.json, keyed by transaction. Each entry holds how
many debit attempts the agent has made, how many times it has contacted the
customer, what it said, and whether the money eventually came in.

The clock is virtual and deliberately so. Rules like the 24-hour notice period
only mean anything if time passes between runs, and nobody is going to wait a
day between demo runs, so each run advances a stored clock by a set number of
hours (24 by default, `--advance-hours` to change it). Everything time-based
is measured against that clock, and it is labelled as simulated wherever it
surfaces.
"""
from __future__ import annotations

import json
import os

from agent import schema

_HERE = os.path.dirname(os.path.abspath(__file__))
MEMORY_PATH = os.path.join(_HERE, "..", "reports", "memory.json")

EMPTY = {"run_count": 0, "clock_hours": 0.0, "transactions": {}}

# Actions that count as a debit attempt, and actions that count as reaching
# out to the customer. Internal escalation is neither: nobody is contacted and
# no debit is tried.
ATTEMPT_ACTIONS = {schema.ACTION_SCHEDULE_RETRY}
CONTACT_ACTIONS = {schema.ACTION_SEND_PAYMENT_LINK, schema.ACTION_ESCALATE_MANUAL_PAYMENT}


def load() -> dict:
    if not os.path.exists(MEMORY_PATH):
        return json.loads(json.dumps(EMPTY))
    with open(MEMORY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(state: dict) -> str:
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return MEMORY_PATH


def reset() -> None:
    if os.path.exists(MEMORY_PATH):
        os.remove(MEMORY_PATH)


def start_run(state: dict, advance_hours: float = 24.0) -> dict:
    """Marks the start of a run and moves the simulated clock forward."""
    state["run_count"] = state.get("run_count", 0) + 1
    if state["run_count"] > 1:
        state["clock_hours"] = state.get("clock_hours", 0.0) + advance_hours
    return state


def _entry(state: dict, txn_id: str) -> dict:
    return state["transactions"].setdefault(txn_id, {
        "attempts_made": 0,
        "contacts_made": 0,
        "escalations_made": 0,
        "last_notice_at_hours": None,
        "messages": [],
        "history": [],
        "resolved": False,
        "resolved_in_run": None,
    })


def apply(state: dict, row: dict) -> dict:
    """Returns a copy of the row with what the agent remembers folded in.

    The CSV values are treated as history that happened before Recur was
    switched on. Anything the agent has done since is added on top, so the
    limits are enforced against the combined total.
    """
    row = dict(row)
    row.setdefault("already_resolved", False)
    row.setdefault("previous_messages", [])
    row.setdefault("escalations_made", 0)

    mem = state.get("transactions", {}).get(row["txn_id"])
    if not mem:
        return row

    row["attempt_count"] = row["attempt_count"] + mem["attempts_made"]
    row["contact_count"] = row["contact_count"] + mem["contacts_made"]
    row["already_resolved"] = mem["resolved"]
    row["escalations_made"] = mem.get("escalations_made", 0)
    row["previous_messages"] = [m["text"] for m in mem["messages"]]

    if mem["last_notice_at_hours"] is not None:
        row["hours_since_notification"] = state["clock_hours"] - mem["last_notice_at_hours"]

    return row


def record(state: dict, row: dict, action: str, recovered: bool, message_text=None) -> None:
    mem = _entry(state, row["txn_id"])
    run = state["run_count"]

    if action in ATTEMPT_ACTIONS:
        mem["attempts_made"] += 1
        # A retry carries the required advance notice, so the clock on that
        # notice restarts here.
        mem["last_notice_at_hours"] = state["clock_hours"]
    if action in CONTACT_ACTIONS:
        mem["contacts_made"] += 1
    if action == schema.ACTION_ESCALATE_HUMAN:
        mem["escalations_made"] += 1

    if message_text:
        mem["messages"].append({"run": run, "action": action, "text": message_text})

    if recovered and not mem["resolved"]:
        mem["resolved"] = True
        mem["resolved_in_run"] = run

    mem["history"].append({"run": run, "action": action, "recovered": recovered})


def summary(state: dict) -> dict:
    txns = state.get("transactions", {})
    return {
        "run_count": state.get("run_count", 0),
        "simulated_hours_elapsed": state.get("clock_hours", 0.0),
        "transactions_remembered": len(txns),
        "resolved_so_far": sum(1 for t in txns.values() if t["resolved"]),
        "total_attempts_made": sum(t["attempts_made"] for t in txns.values()),
        "total_contacts_made": sum(t["contacts_made"] for t in txns.values()),
        "total_escalations_made": sum(t.get("escalations_made", 0) for t in txns.values()),
    }
