#!/usr/bin/env python3
"""CLI entrypoint: runs Recur's full agent loop over the current
batch end to end and writes reports/report.json + reports/report.md.

State carries over between runs (reports/memory.json), so running it a
second time sees what the first run already did.

Usage:
    python agent/scorer.py          # (once) train the scorer
    python run_batch.py             # run the agent over data/current_batch.csv
    python run_batch.py --reset     # start again with no memory
    python run_batch.py --advance-hours 48
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Windows consoles often default to a legacy codepage (cp1252) that can't
# print/write the ₹ symbol — force UTF-8 for both stdout and file writes so
# this runs the same on Windows, Mac, and Linux.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

from agent import memory, pipeline  # noqa: E402
from agent import schema  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH_CSV = os.path.join(HERE, "data", "current_batch.csv")
REPORT_JSON = os.path.join(HERE, "reports", "report.json")
REPORT_MD = os.path.join(HERE, "reports", "report.md")


def render_markdown(result: dict) -> str:
    r = result["report"]
    m = r.get("memory", {})
    lines = [
        "# Recur — Batch Report",
        "",
        f"Run **{m.get('run_count', 1)}**, {m.get('simulated_hours_elapsed', 0):.0f} simulated "
        f"hours since the first run.",
        "",
        f"Every row in the batch: **{r['batch_size']}** transactions.",
        "",
        f"- Total at risk: ₹{r['total_at_risk_inr']:,.0f}",
        f"- Total recovered: ₹{r['total_recovered_inr']:,.0f}",
        f"- Recovery rate: {r['recovery_rate']:.1%}",
        f"- Cases recovered: {r['cases_recovered']} / {r['batch_size']}",
        f"- Decisions fixed by rule checks rather than by the arithmetic: {r['guardrail_forced_decisions']}",
        f"- Left alone because an earlier run already collected: {r.get('skipped_already_paid', 0)}",
        f"- Cumulative across all runs: {m.get('resolved_so_far', 0)} collected, "
        f"{m.get('total_attempts_made', 0)} debit attempts made, "
        f"{m.get('total_contacts_made', 0)} customer contacts",
        "",
        "## Action breakdown",
        "",
    ]
    for action, count in sorted(r["action_breakdown"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {action}: {count}")

    lines += ["", "## By case type", ""]
    for ct, stats in r["by_case_type"].items():
        rate = stats["recovered"] / stats["at_risk"] if stats["at_risk"] else 0
        lines.append(f"- {ct}: {stats['n']} cases, ₹{stats['at_risk']:,.0f} at risk, "
                     f"₹{stats['recovered']:,.0f} recovered ({rate:.1%})")

    lines += ["", f"## Unresolved: {len(r['exceptions'])} cases", ""]
    for e in r["exceptions"][:25]:
        lines.append(f"- {e['txn_id']} ({e['case_type']}, ₹{e['amount']:.0f}): "
                     f"{e['action']}, {e['reason']}")
    if len(r["exceptions"]) > 25:
        lines.append(f"- ... and {len(r['exceptions']) - 25} more (see report.json for the full list)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run Recur over the current batch.")
    parser.add_argument("--reset", action="store_true",
                        help="clear what the agent remembers and start from scratch")
    parser.add_argument("--advance-hours", type=float, default=24.0,
                        help="simulated hours since the previous run (default 24)")
    args = parser.parse_args()

    if not os.path.exists(BATCH_CSV):
        raise SystemExit("data/current_batch.csv not found. Run `python data/generate_data.py` first.")

    if args.reset:
        memory.reset()
        print("Memory cleared.\n")

    result = pipeline.run(BATCH_CSV, advance_hours=args.advance_hours)

    os.makedirs(os.path.dirname(REPORT_JSON), exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    md = render_markdown(result)
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(md)

    print(md)
    print(f"\nFull records and decision log written to:\n  {REPORT_JSON}\n  {result['decision_log_path']}")


if __name__ == "__main__":
    main()
