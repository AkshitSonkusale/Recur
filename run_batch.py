#!/usr/bin/env python3
"""CLI entrypoint: runs Recur's full agent loop over the current
batch end to end and writes reports/report.json + reports/report.md.

Usage:
    python agent/scorer.py          # (once) train the Detective model
    python run_batch.py             # run the agent over data/current_batch.csv
"""
from __future__ import annotations

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

from agent import pipeline  # noqa: E402
from agent import schema  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH_CSV = os.path.join(HERE, "data", "current_batch.csv")
REPORT_JSON = os.path.join(HERE, "reports", "report.json")
REPORT_MD = os.path.join(HERE, "reports", "report.md")


def render_markdown(result: dict) -> str:
    r = result["report"]
    lines = [
        "# Recur — Batch Report",
        "",
        f"Batch size: **{r['batch_size']}** transactions "
        f"(run in full — no cherry-picking).",
        "",
        f"- Total at risk: ₹{r['total_at_risk_inr']:,.0f}",
        f"- Total recovered: ₹{r['total_recovered_inr']:,.0f}",
        f"- Recovery rate: {r['recovery_rate']:.1%}",
        f"- Cases recovered: {r['cases_recovered']} / {r['batch_size']}",
        f"- Decisions forced by compliance guardrails (not EV): {r['guardrail_forced_decisions']}",
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

    lines += ["", f"## Exceptions — {len(r['exceptions'])} unresolved cases (honest, not hidden)", ""]
    for e in r["exceptions"][:25]:
        lines.append(f"- {e['txn_id']} ({e['case_type']}, ₹{e['amount']:.0f}): "
                     f"{e['action']} — {e['reason']}")
    if len(r["exceptions"]) > 25:
        lines.append(f"- ... and {len(r['exceptions']) - 25} more (see report.json for the full list)")

    return "\n".join(lines)


def main():
    if not os.path.exists(BATCH_CSV):
        raise SystemExit("data/current_batch.csv not found — run `python data/generate_data.py` first.")

    result = pipeline.run(BATCH_CSV)

    os.makedirs(os.path.dirname(REPORT_JSON), exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    md = render_markdown(result)
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(md)

    print(md)
    print(f"\nFull records + audit trail written to:\n  {REPORT_JSON}\n  {result['audit_log_path']}")


if __name__ == "__main__":
    main()
