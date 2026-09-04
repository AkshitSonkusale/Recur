#!/usr/bin/env python3
"""Renders reports/dashboard.html from reports/report.json and reports/memory.json.

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
MEMORY_JSON = os.path.join(HERE, "reports", "memory.json")
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
    --surface: #fcfcfb; --page: #f9f9f7; --raised: #ffffff;
    --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #898781;
    --grid: #e1e0d9; --line: rgba(11,11,11,0.10);
    --good: #0ca30c; --bad: #d03b3b;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface: #1a1a19; --page: #0d0d0d; --raised: #232322;
      --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #898781;
      --grid: #2c2c2a; --line: rgba(255,255,255,0.10);
      --good: #0ca30c; --bad: #e66767;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface: #1a1a19; --page: #0d0d0d; --raised: #232322;
    --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #898781;
    --grid: #2c2c2a; --line: rgba(255,255,255,0.10);
    --good: #0ca30c; --bad: #e66767;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181;
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page); color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 40px clamp(20px, 5vw, 64px) 80px; line-height: 1.5;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}

  header {{ margin-bottom: 28px; display: flex; justify-content: space-between;
    align-items: flex-start; gap: 24px; flex-wrap: wrap; }}
  .brand {{ display: flex; align-items: center; gap: 14px; }}
  .brand svg {{ flex-shrink: 0; }}
  h1 {{ margin: 0; font-size: 38px; font-weight: 650; letter-spacing: -0.025em; line-height: 1; }}
  .tagline {{ color: var(--ink-2); font-size: 14px; margin-top: 7px; max-width: 520px; }}
  .status {{ display: flex; align-items: center; gap: 9px; padding: 8px 14px;
    background: var(--surface); border: 1px solid var(--line); border-radius: 999px;
    font-size: 12px; color: var(--ink-2); white-space: nowrap; }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--good);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--good) 22%, transparent); }}

  /* the loop, made visible */
  .pipe {{ display: flex; gap: 0; flex-wrap: wrap; }}
  .step {{ flex: 1; min-width: 165px; padding: 0 18px; border-left: 1px solid var(--line); }}
  .step:first-child {{ padding-left: 0; border-left: none; }}
  .step .n {{ font-size: 10px; color: var(--ink-3); letter-spacing: 0.08em; margin-bottom: 7px; }}
  .step .t {{ font-size: 13px; font-weight: 600; margin-bottom: 5px; }}
  .step .d {{ font-size: 12px; color: var(--ink-3); line-height: 1.45; }}

  /* what's different */
  .diffs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 22px; }}
  .diff {{ border-left: 2px solid var(--s1); padding-left: 15px; }}
  .diff:nth-child(2) {{ border-color: var(--s4); }}
  .diff:nth-child(3) {{ border-color: var(--s3); }}
  .diff:nth-child(4) {{ border-color: var(--s5); }}
  .diff .t {{ font-size: 13px; font-weight: 600; margin-bottom: 5px; }}
  .diff .d {{ font-size: 12px; color: var(--ink-3); line-height: 1.5; }}
  .diff .e {{ font-size: 12px; color: var(--ink-2); margin-top: 7px; }}
  .diff .e b {{ color: var(--ink); }}

  section {{
    background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
    padding: 24px 26px; margin-bottom: 16px;
  }}
  h2 {{
    font-size: 11px; margin: 0 0 20px; color: var(--ink-3); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em;
  }}

  /* hero: the money story as one proportion, not two disconnected numbers */
  .hero {{ display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-end; margin-bottom: 22px; }}
  .hero .big {{ font-size: 40px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.1; }}
  .hero .of {{ font-size: 13px; color: var(--ink-3); margin-top: 4px; }}
  .hero .rate {{ font-size: 22px; font-weight: 600; color: var(--good); }}
  .hero .rate-label {{ font-size: 12px; color: var(--ink-3); }}

  .prop {{ height: 14px; background: var(--grid); border-radius: 7px; overflow: hidden; display: flex; }}
  .prop span {{ display: block; height: 100%; }}
  .prop-key {{ display: flex; gap: 20px; margin-top: 10px; font-size: 12px; color: var(--ink-2); }}
  .prop-key i {{ width: 9px; height: 9px; border-radius: 3px; display: inline-block; margin-right: 6px; }}

  .stats {{ display: flex; flex-wrap: wrap; gap: 28px; padding-top: 20px; border-top: 1px solid var(--line); }}
  .stat .n {{ font-size: 20px; font-weight: 600; }}
  .stat .l {{ font-size: 12px; color: var(--ink-3); margin-top: 2px; }}

  /* run over run */
  .runs {{ display: flex; gap: 44px; align-items: flex-end; }}
  .run {{ flex: 1; max-width: 190px; }}
  .run .cols {{ display: flex; gap: 5px; align-items: flex-end; height: 120px;
    padding-bottom: 8px; border-bottom: 1px solid var(--line); }}
  .run .col {{ flex: 1; max-width: 34px; border-radius: 3px 3px 0 0; min-height: 3px; }}
  .run .cap {{ font-size: 11px; color: var(--ink-3); margin-top: 8px; text-align: center; }}
  .run .cap b {{ display: block; color: var(--ink); font-size: 12px; font-weight: 600; }}

  /* bar rows */
  .bar {{ display: flex; align-items: center; gap: 14px; margin-bottom: 9px; }}
  .bar .lab {{ width: 170px; font-size: 13px; flex-shrink: 0; }}
  .bar .track {{ flex: 1; height: 8px; background: var(--grid); border-radius: 4px; overflow: hidden; max-width: 620px; }}
  .bar .fill {{ height: 100%; border-radius: 4px; }}
  .bar .val {{ font-size: 13px; color: var(--ink-2); font-variant-numeric: tabular-nums;
    min-width: 100px; text-align: right; }}
  .group-label {{ font-size: 11px; color: var(--ink-3); margin: 0 0 10px; letter-spacing: 0.04em; }}
  .group-label:not(:first-child) {{ margin-top: 22px; }}

  .case {{ margin-bottom: 20px; }}
  .case .head {{ display: flex; justify-content: space-between; align-items: baseline;
    font-size: 13px; margin-bottom: 7px; }}
  .case .head b {{ font-weight: 600; }}
  .case .head span {{ color: var(--ink-3); font-size: 12px; }}
  .case .track {{ height: 10px; background: var(--grid); border-radius: 5px; overflow: hidden; }}
  .case .fill {{ height: 100%; background: var(--good); border-radius: 5px; }}

  /* table */
  .filters {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
  select {{
    background: var(--page); border: 1px solid var(--line); border-radius: 7px;
    color: var(--ink); padding: 7px 11px; font-size: 12px; font-family: inherit;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: var(--ink-3); font-weight: 600; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.05em; padding: 9px 10px;
    border-bottom: 1px solid var(--line); }}
  td {{ padding: 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }}
  tr.row {{ cursor: pointer; }}
  tr.row:hover td {{ background: var(--raised); }}
  .num {{ font-variant-numeric: tabular-nums; text-align: right; }}
  .yes {{ color: var(--good); font-weight: 600; }}
  .no {{ color: var(--bad); }}
  .tag {{ font-size: 11px; padding: 2px 7px; border-radius: 5px; border: 1px solid var(--line);
    color: var(--ink-2); white-space: nowrap; }}
  .tag.rule {{ border-color: var(--s4); color: var(--s4); }}
  .detail {{ display: none; }}
  .detail.open {{ display: table-row; }}
  .detail td {{ background: var(--page); padding: 18px 20px; }}
  .msg {{ background: var(--surface); border: 1px solid var(--line); border-left: 3px solid var(--s3);
    border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; font-size: 13px; color: var(--ink); }}
  .msg.rejected {{ border-left-color: var(--s2); }}
  .msg .who {{ font-size: 10px; color: var(--ink-3); text-transform: uppercase;
    letter-spacing: 0.05em; margin-bottom: 6px; }}
  ol.steps {{ margin: 0; padding-left: 20px; font-size: 12px; color: var(--ink-2); }}
  ol.steps li {{ margin-bottom: 5px; }}
  ol.steps b {{ color: var(--ink); font-weight: 600; }}
  .hint {{ font-size: 12px; color: var(--ink-3); margin-top: 12px; }}
  .scroll {{ overflow-x: auto; }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div>
    <div class="brand">
      <svg width="38" height="38" viewBox="0 0 38 38" fill="none" aria-hidden="true">
        <circle cx="19" cy="19" r="17.5" stroke="var(--s1)" stroke-width="2"
                stroke-dasharray="72 22" stroke-linecap="round"/>
        <path d="M19 8.5 L24 13 L19 17.5" stroke="var(--s1)" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        <circle cx="19" cy="19" r="4.5" fill="var(--good)"/>
      </svg>
      <h1>Recur</h1>
    </div>
    <div class="tagline">A recovery agent for money a merchant is owed. It decides what to
    chase, how hard, and when to stop, inside the limits UPI Autopay actually allows.</div>
  </div>
  <div class="status"><span class="dot"></span>Run {run_count} · {sim_hours}h simulated ·
    {batch_size} transactions</div>
</header>

<section>
  <h2>Collected</h2>
  <div class="hero">
    <div>
      <div class="big">₹{recovered_fmt}</div>
      <div class="of">of ₹{at_risk_fmt} outstanding</div>
    </div>
    <div>
      <div class="rate">{recovery_rate_fmt}</div>
      <div class="rate-label">collected this run</div>
    </div>
  </div>
  <div class="prop">
    <span style="width:{collected_pct}%;background:var(--good)"></span>
    <span style="width:{remaining_pct}%;background:var(--grid)"></span>
  </div>
  <div class="prop-key">
    <span><i style="background:var(--good)"></i>Collected</span>
    <span><i style="background:var(--grid)"></i>Still outstanding</span>
  </div>

  <div class="stats">
    <div class="stat"><div class="n">{cases_recovered} / {batch_size}</div><div class="l">cases closed</div></div>
    <div class="stat"><div class="n">{guardrail_count}</div><div class="l">decisions fixed by rules, not economics</div></div>
    <div class="stat"><div class="n">{skipped}</div><div class="l">left alone, already paid</div></div>
    <div class="stat"><div class="n">{resolved_total}</div><div class="l">collected across all {run_count} runs</div></div>
  </div>
</section>

<section>
  <h2>How it decides, every transaction</h2>
  <div class="pipe">
    <div class="step"><div class="n">01</div><div class="t">Score</div>
      <div class="d">A trained classifier estimates how likely this money is to come back.</div></div>
    <div class="step"><div class="n">02</div><div class="t">Check the rules</div>
      <div class="d">NPCI retry limits, notice periods, revocation and contact caps narrow or fix what it may do.</div></div>
    <div class="step"><div class="n">03</div><div class="t">Price the options</div>
      <div class="d">Probability times amount, minus what the action costs. Best net value wins, unless a rule already decided.</div></div>
    <div class="step"><div class="n">04</div><div class="t">Act</div>
      <div class="d">Creates a Razorpay payment link, schedules a retry, escalates to a person, or does nothing.</div></div>
    <div class="step"><div class="n">05</div><div class="t">Write and record</div>
      <div class="d">A model writes the customer message, checks vet it, and the whole chain is logged.</div></div>
  </div>
</section>

<section>
  <h2>Where this differs from a retry script</h2>
  <div class="diffs">
    <div class="diff">
      <div class="t">It counts its own actions</div>
      <div class="d">The four-attempt cap is enforced against attempts this agent made, not a number handed to it in a file. Paid transactions stop being chased.</div>
      <div class="e"><b>{total_attempts}</b> debit attempts and <b>{total_contacts}</b> contacts tracked across {run_count} runs, none over the limit</div>
    </div>
    <div class="diff">
      <div class="t">Compliance outranks the money</div>
      <div class="d">When a rule and the expected value disagree, the rule wins and the log says so, even when standing down costs more than acting.</div>
      <div class="e"><b>{guardrail_count}</b> of {batch_size} decisions this run were taken out of the economics</div>
    </div>
    <div class="diff">
      <div class="t">The model writes, it never decides</div>
      <div class="d">Amount, recipient, channel and whether to make contact are all settled before the language model is called. It only chooses words, and every word is checked.</div>
      <div class="e">{llm_evidence}</div>
    </div>
    <div class="diff">
      <div class="t">Nothing is unexplained</div>
      <div class="d">Every decision keeps the options it rejected, the rules that fired, and the reasoning, so any single outcome can be reconstructed.</div>
      <div class="e"><b>{batch_size}</b> decisions, each fully traceable below</div>
    </div>
  </div>
</section>

{runs_section}

<section>
  <h2>What it did</h2>
  {action_bars}
</section>

<section>
  <h2>By case type</h2>
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
  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th>Txn</th><th>Case</th><th class="num">Amount</th><th>Action</th>
          <th>Decided by</th><th class="num">P(pay)</th><th class="num">Net value</th><th>Paid</th>
        </tr>
      </thead>
      <tbody id="log-tbody"></tbody>
    </table>
  </div>
  <p class="hint">Click any row for the full reasoning and the message that went out.</p>
</section>

</div>

<script id="records-data" type="application/json">{records_json}</script>
<script>
  const records = JSON.parse(document.getElementById('records-data').textContent);
  const actionLabels = {action_labels_json};
  const caseLabels = {case_labels_json};
  const money = n => '₹' + Math.round(n).toLocaleString('en-IN');

  function render() {{
    const f = id => document.getElementById(id).value;
    const rows = records.filter(r =>
      (!f('f-case') || r.case_type === f('f-case')) &&
      (!f('f-action') || r.action === f('f-action')) &&
      (!f('f-recovered') || String(r.recovered) === f('f-recovered')) &&
      (!f('f-basis') || r.decision_basis === f('f-basis')) &&
      (!f('f-msg') || r.message_source === f('f-msg'))
    );

    const tb = document.getElementById('log-tbody');
    tb.innerHTML = '';
    rows.forEach(r => {{
      const isRule = r.decision_basis === 'compliance_override';
      const tr = document.createElement('tr');
      tr.className = 'row';
      tr.innerHTML = `
        <td>${{r.txn_id}}</td>
        <td>${{caseLabels[r.case_type] || r.case_type}}</td>
        <td class="num">${{money(r.amount)}}</td>
        <td>${{actionLabels[r.action] || r.action}}</td>
        <td><span class="tag ${{isRule ? 'rule' : ''}}">${{isRule ? 'Rule check' : 'Expected value'}}</span></td>
        <td class="num">${{(r.probability_used*100).toFixed(0)}}%</td>
        <td class="num">${{money(r.net_ev)}}</td>
        <td class="${{r.recovered ? 'yes' : 'no'}}">${{r.recovered ? 'Yes' : 'No'}}</td>`;

      const d = document.createElement('tr');
      d.className = 'detail';
      const rejected = r.message_source === 'template_after_failed_check';
      const who = r.message_source === 'llm' ? 'Written by the model, passed every check'
                : rejected ? 'Model output rejected (' + r.message_rejection_reason + '), template sent'
                : 'Fixed template';
      const msg = r.message_text
        ? `<div class="msg ${{rejected ? 'rejected' : ''}}"><div class="who">${{who}}</div>${{r.message_text}}</div>`
        : '';
      const steps = r.steps.map(s =>
        `<li><b>${{s.step.replace(/_/g,' ')}}</b> ${{s.detail}}</li>`).join('');
      d.innerHTML = `<td colspan="8">${{msg}}<ol class="steps">${{steps}}</ol></td>`;

      tr.addEventListener('click', () => d.classList.toggle('open'));
      tb.appendChild(tr); tb.appendChild(d);
    }});
  }}

  ['f-case','f-action','f-recovered','f-basis','f-msg']
    .forEach(id => document.getElementById(id).addEventListener('change', render));
  render();
</script>
</body>
</html>
"""


def bar_rows(rows, max_value, color_fn):
    out = []
    for label, value, key in rows:
        pct = 0 if not max_value else max(2, round(100 * value / max_value))
        out.append(
            f'<div class="bar"><div class="lab">{label}</div>'
            f'<div class="track"><div class="fill" style="width:{pct}%;background:{color_fn(key)}"></div></div>'
            f'<div class="val">{value}</div></div>'
        )
    return "\n".join(out)


def build_action_section(breakdown: dict) -> str:
    """Split into what it did and what it deliberately didn't, because the
    restraint is the interesting half."""
    acted = {k: v for k, v in breakdown.items() if k != "do_nothing"}
    stood = breakdown.get("do_nothing", 0)
    biggest = max(list(acted.values()) + [stood, 1])

    rows = sorted(acted.items(), key=lambda kv: -kv[1])
    html = ['<div class="group-label">ACTED</div>']
    html.append(bar_rows([(ACTION_LABELS.get(a, a), c, a) for a, c in rows], biggest,
                          lambda a: f"var(--s{ACTION_COLOR_SLOT.get(a, 1)})"))
    html.append('<div class="group-label">STOOD DOWN</div>')
    html.append(bar_rows([("Took no action", stood, "do_nothing")], biggest,
                          lambda a: "var(--s5)"))
    return "\n".join(html)


def build_case_section(by_case: dict) -> str:
    out = []
    for ct, s in by_case.items():
        pct = 0 if not s["at_risk"] else round(100 * s["recovered"] / s["at_risk"])
        out.append(f"""
        <div class="case">
          <div class="head">
            <b>{CASE_LABELS.get(ct, ct)}</b>
            <span>₹{round(s['recovered']):,} of ₹{round(s['at_risk']):,} · {s['n']} cases · {pct}%</span>
          </div>
          <div class="track"><div class="fill" style="width:{max(pct, 1)}%"></div></div>
        </div>""")
    return "\n".join(out)


def build_runs_section() -> str:
    """Per-run history, which is the part that shows the agent winding down."""
    if not os.path.exists(MEMORY_JSON):
        return ""
    with open(MEMORY_JSON, encoding="utf-8") as f:
        mem = json.load(f)

    runs: dict = {}
    for txn in mem.get("transactions", {}).values():
        for h in txn.get("history", []):
            r = runs.setdefault(h["run"], {"acted": 0, "stood": 0, "paid": 0})
            if h["action"] == "do_nothing":
                r["stood"] += 1
            else:
                r["acted"] += 1
            if h["recovered"]:
                r["paid"] += 1

    if len(runs) < 2:
        return """
        <section>
          <h2>Across runs</h2>
          <p class="hint" style="margin:0">Run <code>python run_batch.py</code> again to see this fill in.
          The agent remembers what it already did, so repeat runs chase fewer people:
          paid transactions drop out, retry and contact limits fill up, and it goes quiet.</p>
        </section>"""

    tallest = max(max(r["acted"], r["stood"]) for r in runs.values()) or 1
    cols = []
    for run in sorted(runs):
        r = runs[run]
        h_act = max(3, round(130 * r["acted"] / tallest))
        h_stood = max(3, round(130 * r["stood"] / tallest))
        h_paid = max(3, round(130 * r["paid"] / tallest))
        cols.append(f"""
        <div class="run">
          <div class="cols">
            <div class="col" style="height:{h_act}px;background:var(--s1)" title="acted"></div>
            <div class="col" style="height:{h_paid}px;background:var(--good)" title="paid"></div>
            <div class="col" style="height:{h_stood}px;background:var(--s5)" title="stood down"></div>
          </div>
          <div class="cap"><b>Run {run}</b>{r['acted']} acted · {r['paid']} paid · {r['stood']} quiet</div>
        </div>""")

    return f"""
    <section>
      <h2>Across runs</h2>
      <div class="runs">{''.join(cols)}</div>
      <div class="prop-key" style="margin-top:16px">
        <span><i style="background:var(--s1)"></i>Acted on</span>
        <span><i style="background:var(--good)"></i>Paid</span>
        <span><i style="background:var(--s5)"></i>Left alone</span>
      </div>
      <p class="hint">Limits are counted against what the agent itself did, so it chases
      fewer people each run rather than starting fresh every time.</p>
    </section>"""


def main():
    with open(REPORT_JSON, encoding="utf-8") as f:
        data = json.load(f)
    report, records = data["report"], data["records"]
    mem = report.get("memory", {})

    at_risk = report["total_at_risk_inr"]
    collected = report["total_recovered_inr"]
    collected_pct = 0 if not at_risk else round(100 * collected / at_risk, 1)

    llm_written = sum(1 for r in records if r.get("message_source") == "llm")
    llm_rejected = sum(1 for r in records
                       if r.get("message_source") == "template_after_failed_check")
    if llm_written or llm_rejected:
        llm_evidence = (f"<b>{llm_written}</b> messages written by the model, "
                        f"<b>{llm_rejected}</b> rejected by the checks and replaced")
    else:
        llm_evidence = ("Running on fixed templates. Set <b>GROQ_API_KEY</b> in .env "
                        "to have the model write them instead.")

    html = TEMPLATE.format(
        llm_evidence=llm_evidence,
        total_attempts=mem.get("total_attempts_made", 0),
        total_contacts=mem.get("total_contacts_made", 0),
        run_count=mem.get("run_count", 1),
        sim_hours=f"{mem.get('simulated_hours_elapsed', 0):.0f}",
        batch_size=report["batch_size"],
        at_risk_fmt=f"{round(at_risk):,}",
        recovered_fmt=f"{round(collected):,}",
        recovery_rate_fmt=f"{report['recovery_rate']*100:.1f}%",
        collected_pct=collected_pct,
        remaining_pct=round(100 - collected_pct, 1),
        cases_recovered=report["cases_recovered"],
        guardrail_count=report["guardrail_forced_decisions"],
        skipped=report.get("skipped_already_paid", 0),
        resolved_total=mem.get("resolved_so_far", 0),
        runs_section=build_runs_section(),
        action_bars=build_action_section(report["action_breakdown"]),
        case_bars=build_case_section(report["by_case_type"]),
        case_options="".join(f'<option value="{c}">{l}</option>' for c, l in CASE_LABELS.items()),
        action_options="".join(f'<option value="{a}">{l}</option>' for a, l in ACTION_LABELS.items()),
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
