#!/usr/bin/env python3
"""Renders reports/dashboard.html from reports/report.json.

Read-only. It doesn't import anything from agent/ and doesn't recompute
figures, it just displays what run_batch.py already wrote. Run it after
run_batch.py to refresh the page.

Usage:
    python make_dashboard.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_JSON = os.path.join(HERE, "reports", "report.json")
OUT_HTML = os.path.join(HERE, "reports", "dashboard.html")

ACTION_LABELS = {
    "schedule_retry": "Schedule retry",
    "send_payment_link": "Send payment link",
    "escalate_manual_payment": "Escalate: manual payment",
    "escalate_human": "Escalate: human",
    "do_nothing": "Stand down",
}
ACTION_COLOR_SLOT = {
    "schedule_retry": 1,
    "send_payment_link": 2,
    "escalate_manual_payment": 3,
    "escalate_human": 4,
    "do_nothing": 5,
}
CASE_LABELS = {
    "mandate_failure": "Mandate failure",
    "checkout_abandonment": "Checkout abandonment",
    "receivable_overdue": "Receivable overdue",
}

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Recur — Batch Report</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --grid: #e1e0d9;
    --border: rgba(11,11,11,0.10);
    --good: #0ca30c;
    --critical: #d03b3b;
    --slot-1: #2a78d6; --slot-2: #eb6834; --slot-3: #1baf7a;
    --slot-4: #eda100; --slot-5: #e87ba4;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
      --good: #0ca30c; --critical: #e66767;
      --slot-1: #3987e5; --slot-2: #d95926; --slot-3: #199e70;
      --slot-4: #c98500; --slot-5: #d55181;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
    --good: #0ca30c; --critical: #e66767;
    --slot-1: #3987e5; --slot-2: #d95926; --slot-3: #199e70;
    --slot-4: #c98500; --slot-5: #d55181;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 32px clamp(16px, 4vw, 48px) 64px;
  }}
  header {{ margin-bottom: 28px; }}
  header h1 {{ margin: 0 0 4px; font-size: 22px; letter-spacing: -0.01em; }}
  header p {{ margin: 0; color: var(--text-secondary); font-size: 14px; }}
  .badge-guardrail {{
    display: inline-block; margin-top: 10px; padding: 4px 10px; border-radius: 999px;
    background: var(--surface-1); border: 1px solid var(--border);
    color: var(--text-secondary); font-size: 12px;
  }}

  .tiles {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px; margin-bottom: 28px;
  }}
  .tile {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 18px;
  }}
  .tile .label {{ font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }}
  .tile .value {{ font-size: 26px; font-weight: 600; letter-spacing: -0.01em; }}
  .tile .sub {{ font-size: 12px; color: var(--text-secondary); margin-top: 4px; }}

  section {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 22px; margin-bottom: 20px;
  }}
  section h2 {{ font-size: 14px; margin: 0 0 16px; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }}

  .bar-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }}
  .bar-row .bar-label {{ width: 190px; font-size: 13px; color: var(--text-primary); flex-shrink: 0; }}
  .bar-track {{ flex: 1; height: 10px; background: var(--grid); border-radius: 4px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 4px; }}
  .bar-value {{ width: 130px; text-align: right; font-size: 13px; color: var(--text-secondary);
    font-variant-numeric: tabular-nums; flex-shrink: 0; }}

  .case-block {{ margin-bottom: 18px; }}
  .case-block .title {{ font-size: 13px; margin-bottom: 6px; font-weight: 600; }}
  .legend {{ display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin-bottom: 14px; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}

  .filters {{ display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }}
  .filters select, .filters input {{
    background: var(--page); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text-primary); padding: 6px 10px; font-size: 13px; font-family: inherit;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: var(--text-muted); font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.03em; padding: 8px 10px; border-bottom: 1px solid var(--grid); }}
  td {{ padding: 8px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }}
  tr.row:hover {{ background: var(--page); cursor: pointer; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; color: #fff; }}
  .status-good {{ color: var(--good); font-weight: 600; }}
  .status-critical {{ color: var(--critical); font-weight: 600; }}
  .amount {{ font-variant-numeric: tabular-nums; }}
  .detail-row td {{ background: var(--page); font-size: 12px; color: var(--text-secondary); }}
  .detail-row {{ display: none; }}
  .detail-row.open {{ display: table-row; }}
  .steps {{ margin: 0; padding-left: 18px; }}
  .steps li {{ margin-bottom: 4px; }}
  .msg {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 12px; margin-bottom: 10px; color: var(--text-primary); font-size: 13px; }}
  .msg-tag {{ font-size: 11px; color: var(--text-muted); margin-bottom: 5px;
    text-transform: uppercase; letter-spacing: 0.03em; }}
  .hint {{ font-size: 12px; color: var(--text-muted); margin-top: 10px; }}
  .table-wrap {{ overflow-x: auto; }}
</style>
</head>
<body>

<header>
  <h1>Recur — Batch Report</h1>
  <p>Run {run_count}, {sim_hours} simulated hours in. Every row in the batch: {batch_size} transactions.</p>
  <span class="badge-guardrail">{guardrail_count} of {batch_size} decisions were fixed by rule checks rather than by the arithmetic</span>
</header>

<div class="tiles">
  <div class="tile"><div class="label">Outstanding</div><div class="value">₹{at_risk_fmt}</div></div>
  <div class="tile"><div class="label">Collected</div><div class="value">₹{recovered_fmt}</div></div>
  <div class="tile"><div class="label">Collected rate</div><div class="value">{recovery_rate_fmt}</div></div>
  <div class="tile"><div class="label">Cases closed</div><div class="value">{cases_recovered} / {batch_size}</div></div>
  <div class="tile"><div class="label">Fixed by rules</div><div class="value">{guardrail_count}</div><div class="sub">rule beat arithmetic</div></div>
  <div class="tile"><div class="label">Left alone</div><div class="value">{skipped}</div><div class="sub">already paid earlier</div></div>
  <div class="tile"><div class="label">Collected to date</div><div class="value">{resolved_total}</div><div class="sub">across {run_count} runs</div></div>
</div>

<section>
  <h2>Action breakdown</h2>
  {action_bars}
</section>

<section>
  <h2>By case type</h2>
  <div class="legend">
    <span><span class="swatch" style="background:var(--grid)"></span>Outstanding</span>
    <span><span class="swatch" style="background:var(--good)"></span>Collected</span>
  </div>
  {case_bars}
</section>

<section>
  <h2>Decision log</h2>
  <div class="filters">
    <select id="f-case"><option value="">All case types</option>{case_options}</select>
    <select id="f-action"><option value="">All actions</option>{action_options}</select>
    <select id="f-recovered">
      <option value="">Paid: any</option>
      <option value="true">Paid</option>
      <option value="false">Not paid</option>
    </select>
    <select id="f-basis">
      <option value="">Decided by: any</option>
      <option value="expected_value">Expected value</option>
      <option value="compliance_override">Rule check</option>
    </select>
    <select id="f-msg">
      <option value="">Message: any</option>
      <option value="llm">Written by model</option>
      <option value="template_after_failed_check">Model output rejected</option>
      <option value="template">Template</option>
    </select>
  </div>
  <div class="table-wrap">
    <table id="log-table">
      <thead>
        <tr>
          <th>Txn</th><th>Case type</th><th>Amount</th><th>Action</th>
          <th>Decided by</th><th>P(recover)</th><th>Net EV</th><th>Paid</th>
        </tr>
      </thead>
      <tbody id="log-tbody"></tbody>
    </table>
  </div>
  <p class="hint">Click any row to see how that decision was made and what was sent.</p>
</section>

<script id="records-data" type="application/json">{records_json}</script>
<script>
  const records = JSON.parse(document.getElementById('records-data').textContent);
  const actionLabels = {action_labels_json};
  const caseLabels = {case_labels_json};

  function fmtAmount(n) {{ return '₹' + Math.round(n).toLocaleString('en-IN'); }}

  function render() {{
    const caseF = document.getElementById('f-case').value;
    const actionF = document.getElementById('f-action').value;
    const recF = document.getElementById('f-recovered').value;
    const basisF = document.getElementById('f-basis').value;
    const msgF = document.getElementById('f-msg').value;

    const rows = records.filter(r =>
      (!caseF || r.case_type === caseF) &&
      (!actionF || r.action === actionF) &&
      (!recF || String(r.recovered) === recF) &&
      (!basisF || r.decision_basis === basisF) &&
      (!msgF || r.message_source === msgF)
    );

    const tbody = document.getElementById('log-tbody');
    tbody.innerHTML = '';
    rows.forEach((r, i) => {{
      const tr = document.createElement('tr');
      tr.className = 'row';
      tr.innerHTML = `
        <td>${{r.txn_id}}</td>
        <td>${{caseLabels[r.case_type] || r.case_type}}</td>
        <td class="amount">${{fmtAmount(r.amount)}}</td>
        <td>${{actionLabels[r.action] || r.action}}</td>
        <td>${{r.decision_basis === 'compliance_override' ? 'Rule check' : 'Expected value'}}</td>
        <td class="amount">${{(r.probability_used*100).toFixed(0)}}%</td>
        <td class="amount">${{fmtAmount(r.net_ev)}}</td>
        <td class="${{r.recovered ? 'status-good' : 'status-critical'}}">${{r.recovered ? 'Yes' : 'No'}}</td>
      `;
      const detail = document.createElement('tr');
      detail.className = 'detail-row';
      const steps = r.steps.map(s => `<li><strong>${{s.step.replace(/_/g,' ')}}:</strong> ${{s.detail}}</li>`).join('');
      const msg = r.message_text ? `
        <div class="msg">
          <div class="msg-tag">${{
            r.message_source === 'llm' ? 'Written by the model, passed all checks'
            : r.message_source === 'template_after_failed_check' ? 'Model output rejected (' + r.message_rejection_reason + '), template sent'
            : 'Fixed template'
          }}</div>
          ${{r.message_text}}
        </div>` : '';
      detail.innerHTML = `<td colspan="8">${{msg}}<ol class="steps">${{steps}}</ol></td>`;
      tr.addEventListener('click', () => detail.classList.toggle('open'));
      tbody.appendChild(tr);
      tbody.appendChild(detail);
    }});
  }}

  ['f-case', 'f-action', 'f-recovered', 'f-basis', 'f-msg'].forEach(id =>
    document.getElementById(id).addEventListener('change', render)
  );
  render();
</script>

</body>
</html>
"""


def bar_html(rows, max_value, color_fn):
    out = []
    for label, value, key in rows:
        pct = 0 if max_value == 0 else max(2, round(100 * value / max_value))
        out.append(
            f'<div class="bar-row"><div class="bar-label">{label}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color_fn(key)}"></div></div>'
            f'<div class="bar-value">{value}</div></div>'
        )
    return "\n".join(out)


def case_bar_block(case_type, stats, max_amount):
    label = CASE_LABELS.get(case_type, case_type)
    at_risk_pct = 0 if max_amount == 0 else max(2, round(100 * stats["at_risk"] / max_amount))
    rec_pct = 0 if max_amount == 0 else max(2, round(100 * stats["recovered"] / max_amount))
    return f"""
    <div class="case-block">
      <div class="title">{label} — {stats['n']} cases</div>
      <div class="bar-row"><div class="bar-label">Outstanding</div>
        <div class="bar-track"><div class="bar-fill" style="width:{at_risk_pct}%;background:var(--grid)"></div></div>
        <div class="bar-value">₹{round(stats['at_risk']):,}</div></div>
      <div class="bar-row"><div class="bar-label">Collected</div>
        <div class="bar-track"><div class="bar-fill" style="width:{rec_pct}%;background:var(--good)"></div></div>
        <div class="bar-value">₹{round(stats['recovered']):,}</div></div>
    </div>
    """


def main():
    with open(REPORT_JSON, encoding="utf-8") as f:
        data = json.load(f)
    report = data["report"]
    records = data["records"]

    action_rows = sorted(report["action_breakdown"].items(), key=lambda kv: -kv[1])
    max_action = max(report["action_breakdown"].values()) if report["action_breakdown"] else 1
    action_bars = bar_html(
        [(ACTION_LABELS.get(a, a), c, a) for a, c in action_rows],
        max_action,
        lambda a: f"var(--slot-{ACTION_COLOR_SLOT.get(a, 1)})",
    )

    max_amount = max((s["at_risk"] for s in report["by_case_type"].values()), default=1)
    case_bars = "\n".join(
        case_bar_block(ct, stats, max_amount) for ct, stats in report["by_case_type"].items()
    )

    case_options = "".join(f'<option value="{c}">{l}</option>' for c, l in CASE_LABELS.items())
    action_options = "".join(f'<option value="{a}">{l}</option>' for a, l in ACTION_LABELS.items())

    html = TEMPLATE.format(
        batch_size=report["batch_size"],
        guardrail_count=report["guardrail_forced_decisions"],
        at_risk_fmt=f"{round(report['total_at_risk_inr']):,}",
        recovered_fmt=f"{round(report['total_recovered_inr']):,}",
        recovery_rate_fmt=f"{report['recovery_rate']*100:.1f}%",
        cases_recovered=report["cases_recovered"],
        run_count=report.get("memory", {}).get("run_count", 1),
        sim_hours=f"{report.get('memory', {}).get('simulated_hours_elapsed', 0):.0f}",
        skipped=report.get("skipped_already_paid", 0),
        resolved_total=report.get("memory", {}).get("resolved_so_far", 0),
        action_bars=action_bars,
        case_bars=case_bars,
        case_options=case_options,
        action_options=action_options,
        records_json=json.dumps(records),
        action_labels_json=json.dumps(ACTION_LABELS),
        case_labels_json=json.dumps(CASE_LABELS),
    )

    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
