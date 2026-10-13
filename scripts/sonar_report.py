#!/usr/bin/env python3
"""Generate SonarQube quality gate report as HTML (for screenshotting)."""
from pathlib import Path

import requests

PROJECT_KEY = "chalice-devops-lab"
GATE_NAME = "chalice-devops-lab-gate"
ADMIN_FILE = Path(__file__).parent.parent / ".sonar" / "admin-credentials"

with open(ADMIN_FILE) as f:
    username, password = f.read().strip().split(":", 1)

AUTH = (username, password)
HOST = "http://localhost:9000"

def get(path, **params):
    r = requests.get(f"{HOST}{path}", params=params, auth=AUTH, timeout=10)
    r.raise_for_status()
    return r.json()

# --- project status (Community: only Cayc conditions) ---
status = get("/api/qualitygates/project_status", projectKey=PROJECT_KEY)["projectStatus"]
project_status = status["status"]
cayc_conditions = status.get("conditions", [])
cayc = status.get("caycStatus", "unknown")

# --- gate definition (all conditions) ---
gate = get("/api/qualitygates/show", name=GATE_NAME)
gate_conditions = gate.get("conditions", [])

# --- measures for local evaluation ---
measure_keys = ",".join(sorted({c["metric"] for c in gate_conditions} | {"alert_status"}))
measures = {m["metric"]: m.get("value", "n/a") for m in get(
    "/api/measures/component", component=PROJECT_KEY, metricKeys=measure_keys
).get("component", {}).get("measures", [])}

def evaluate(cond):
    """Local evaluation (Community edition doesn't return non-Cayc conditions)."""
    metric, op, threshold = cond["metric"], cond["op"], cond["error"]
    actual = measures.get(metric, "n/a")
    if actual == "n/a":
        return "SKIP", "n/a", threshold
    try:
        a, t = float(actual), float(threshold)
    except ValueError:
        return "SKIP", actual, threshold
    # GT: fail if actual > threshold ; LT: fail if actual < threshold
    if op == "GT":
        ok = a <= t
    elif op == "LT":
        ok = a >= t
    else:
        ok = True
    return ("PASS" if ok else "FAIL"), actual, threshold

rows = []
for cond in gate_conditions:
    verdict, actual, threshold = evaluate(cond)
    cls = {"PASS": "pass", "FAIL": "fail", "SKIP": "skip"}[verdict]
    rows.append(
        f'<tr><td>{cond["metric"]}</td><td>{cond["op"]}</td>'
        f'<td>{threshold}</td><td>{actual}</td>'
        f'<td class="{cls}">{verdict}</td></tr>'
    )

metric_rows = "".join(
    f'<p><strong>{k}:</strong> {v}</p>' for k, v in sorted(measures.items())
)

badge_class = "status-OK" if project_status == "OK" else "status-ERR"

html = f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>SonarQube Quality Gate Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; background: #1d1d1d; color: #fff; }}
    h1 {{ color: #7F00FF; }}
    .status-badge {{ display: inline-block; padding: 15px 40px; border-radius: 8px; font-size: 32px; font-weight: bold; margin: 20px 0; }}
    .status-OK {{ background: #00C853; color: #000; }}
    .status-ERR {{ background: #ff1744; color: #fff; }}
    table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
    th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #444; }}
    th {{ background: #2d2d2d; color: #7F00FF; }}
    .pass {{ color: #00C853; font-weight: bold; }}
    .fail {{ color: #ff1744; font-weight: bold; }}
    .skip {{ color: #9e9e9e; font-weight: bold; }}
    .cayc {{ margin-top: 30px; padding: 20px; background: #2d2d2d; border-radius: 8px; }}
    .note {{ color: #9e9e9e; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>SonarQube Quality Gate Report</h1>
  <h2>Project: AWS Chalice DevOps Lab</h2>
  <div class="status-badge {badge_class}">Quality Gate: {project_status}</div>

  <h3>Gate Conditions ({GATE_NAME})</h3>
  <table>
    <tr><th>Metric</th><th>Operator</th><th>Threshold</th><th>Actual</th><th>Verdict</th></tr>
    {"".join(rows)}
  </table>
  <p class="note">Community edition only reports Clean-As-You-Code conditions via API;
  overall conditions are evaluated locally against project measures (same logic as scripts/validation/quality_gate.sh).</p>

  <div class="cayc">
    <h3>Clean As You Code (CAYC)</h3>
    <p>Status: <strong>{cayc}</strong></p>
    <p>Conditions reported by server: {len(cayc_conditions)}</p>
  </div>

  <div style="margin-top: 40px; padding: 20px; background: #2d2d2d; border-radius: 8px;">
    <h3>Project Measures</h3>
    {metric_rows}
  </div>
</body>
</html>'''

TMP_DIR = Path(__file__).parent.parent / "tmp"
TMP_DIR.mkdir(exist_ok=True)
REPORT_PATH = TMP_DIR / "sonar-report.html"

with open(REPORT_PATH, "w") as f:
    f.write(html)

print(f"Generated {REPORT_PATH} (status={project_status}, conditions={len(rows)})")
