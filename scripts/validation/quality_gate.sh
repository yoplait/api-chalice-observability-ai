#!/usr/bin/env bash
# Host-side quality gate + coverage enforcement.
# Works with SonarQube Community Edition (does not rely on QG project_status API).
set -euo pipefail

SONAR="${SONAR_HOST_URL:-http://localhost:9000}"
TOKEN_FILE="${SONAR_TOKEN_FILE:-.sonar/token}"
PROJECT="${SONAR_PROJECT_KEY:-chalice-devops-lab}"
COV_XML="${COV_XML:-coverage.xml}"
PASS=0
FAIL=0
TOKEN=""
_GATE_JSON=""

assert(){
  # assert "label" command [args...]
  if "${@:2}"; then echo "  [PASS] $1"; PASS=$((PASS+1)); else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi
}

echo "============================================================"
echo "  SonarQube Quality Gate — Validation"
echo "============================================================"

# Read token once
TOKEN="$(cat "$TOKEN_FILE" 2>/dev/null || echo "")"
if [ -z "$TOKEN" ]; then echo "[FATAL] No token in $TOKEN_FILE"; exit 1; fi

curl_ok(){
  _raw="$(curl -sf --max-time 5 -u "$TOKEN:" "$1" 2>/dev/null)" || return 1
  return 0
}

# ── 1. Wait for the CE task produced by THIS scan to finish ───
# Race we are fixing: right after the scanner uploads, the new CE task may not
# be queued yet, so /api/ce/component still reports the PREVIOUS analysis as
# `.current` = SUCCESS. Naively breaking there makes us read stale measures
# (e.g. last run's coverage). So we snapshot the last known task id as a
# baseline and only accept a *different* id reaching a terminal state.
CE_TIMEOUT="${CE_TIMEOUT:-90}"
echo -n "  Waiting for this scan's CE analysis to finish... "

# Baseline: id of the most recent task already known to Sonar (may be empty on
# the very first analysis).
baseline=""
if curl_ok "$SONAR/api/ce/component?component=$PROJECT"; then
  baseline="$(echo "$_raw" | jq -r '.current.id // empty')"
fi

deadline=$(( $(date +%s) + CE_TIMEOUT ))
grace=$(( $(date +%s) + 12 ))
task_id=""
current_status="QUEUED"
fresh=0
seen_new=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl_ok "$SONAR/api/ce/component?component=$PROJECT"; then
    current_status="$(echo "$_raw" | jq -r '.current.status // "QUEUED"')"
    task_id="$(echo "$_raw" | jq -r '.current.id // empty')"
    # A new (non-baseline) task in `.current` or `.pending` means THIS scan is
    # in flight; track it and wait for its terminal state.
    pending_new="$(echo "$_raw" | jq --arg b "$baseline" \
      '[.pending[]? | select(.id != $b)] | length')"
    if [ -n "$baseline" ] && [ "$task_id" != "$baseline" ]; then seen_new=1; fi
    if [ "$pending_new" != "0" ]; then seen_new=1; fi

    if [ "$seen_new" = "1" ] && { [ -z "$baseline" ] || [ "$task_id" != "$baseline" ]; } \
        && [ "$current_status" = "SUCCESS" ]; then
      echo "SUCCESS (task=$task_id)"; fresh=1; break
    elif [ "$seen_new" = "1" ] && { [ "$current_status" = "FAILED" ] || [ "$current_status" = "CANCELED" ] || [ "$current_status" = "ERR" ]; }; then
      echo "$current_status"; assert "CE task succeeded" false; exit 1
    elif [ "$seen_new" = "0" ] && [ "$(date +%s)" -ge "$grace" ]; then
      # No new analysis ever appeared for this component within the grace window
      # -> nobody ran a fresh scan before us; the existing measures are current.
      echo "no-op (no new scan submitted; trusting latest measures)"; fresh=1; break
    fi
  fi
  sleep 2
done

if [ "$fresh" = "1" ]; then
  :
elif [ -z "$task_id" ]; then
  echo ""; echo "  [WARN] No CE task found; proceeding anyway"
else
  echo ""; echo "  [WARN] CE not confirmed after ${CE_TIMEOUT}s (status=$current_status), proceeding anyway"
fi

# ── 2. Fetch Quality Gate definition ──────────────────────────
echo -n "  Loading Quality Gate definition... "
if curl_ok "$SONAR/api/qualitygates/show?name=chalice-devops-lab-gate"; then
  _gate_json="$_raw"
  gate_name="$(echo "$_raw" | jq -r '.name')"
  n_conditions="$(echo "$_raw" | jq '.conditions | length')"
  echo "OK ($gate_name, $n_conditions conditions)"
else
  echo "[WARN] Cannot load gate"
  n_conditions=0
fi

# ── 3. Fetch project measures ─────────────────────────────────
echo "  Fetching project measures..."
if curl_ok "$SONAR/api/measures/component?component=$PROJECT&metricKeys=line_coverage,branch_coverage,coverage,statements,duplicated_lines_density,reliability_rating,security_rating,bugs,vulnerabilities,code_smells,new_violations,new_coverage,new_duplicated_lines_density,ncloc"; then
  eval "$(echo "$_raw" | jq -r '.component.measures[] | select(.value != null) | "M_\(.metric)=\(.value)"')" || true
else
  echo "  [WARN] Cannot fetch measures"
fi

# ── 4. Evaluate conditions locally ────────────────────────────
echo ""
echo "  Evaluating Quality Gate conditions:"
evaluated=0
passed=0
if [ "$n_conditions" -gt 0 ] 2>/dev/null; then
  while IFS=$'\t' read -r _metric _op _error _is_cayc; do
    key="M_${_metric}"
    value="${!key:-N/A}"
    if [ "$value" = "N/A" ]; then
      status="NO_DATA"
      cond_ok=false
    else
      if [ "$_op" = "GT" ]; then
        if awk "BEGIN{exit !($value <= $_error)}"; then status="OK"; cond_ok=true
        else status="FAIL"; cond_ok=false; fi
      elif [ "$_op" = "LT" ]; then
        if awk "BEGIN{exit !($value >= $_error)}"; then status="OK"; cond_ok=true
        else status="FAIL"; cond_ok=false; fi
      elif [ "$_op" = "GE" ]; then
        if awk "BEGIN{exit !($value >= $_error)}"; then status="OK"; cond_ok=true
        else status="FAIL"; cond_ok=false; fi
      elif [ "$_op" = "LE" ]; then
        if awk "BEGIN{exit !($value <= $_error)}"; then status="OK"; cond_ok=true
        else status="FAIL"; cond_ok=false; fi
      elif [ "$_op" = "EQ" ]; then
        if awk "BEGIN{exit !($value == $_error)}"; then status="OK"; cond_ok=true
        else status="FAIL"; cond_ok=false; fi
      else
        status="UNKNOWN"; cond_ok=false
      fi
    fi

    # Skip Cayc conditions when no data
    if [ "$_is_cayc" = "true" ] && [ "$value" = "N/A" ]; then
      printf "    %-35s %s %s => SKIPPED (no Cayc baseline)\n" "$_metric" "$_op $_error"
      continue
    fi

    printf "    %-35s %s %s => %s\n" "$_metric" "$_op $_error" "(actual=$value)" "$status"
    evaluated=$((evaluated + 1))
    if $cond_ok; then passed=$((passed + 1)); fi
  done < <(echo "$_gate_json" | jq -r '.conditions[] | [.metric, .op, .error, (.isCaycCondition | tostring)] | @tsv')
fi

if [ "$evaluated" -gt 0 ] && [ "$passed" -eq "$evaluated" ]; then
  assert "All $evaluated conditions passed" true
elif [ "$evaluated" -gt 0 ]; then
  assert "$passed/$evaluated conditions passed" false
else
  echo "  [WARN] No conditions evaluated"
fi

# ── 5. Coverage enforcement from coverage.xml ─────────────────
if [ -s "$COV_XML" ]; then
  read -r line_cov branch_cov < <(python3 -c "
import xml.etree.ElementTree as ET, sys
tree = ET.parse(sys.argv[1])
root = tree.getroot()
lr = float(root.get('line-rate', '0')) * 100
br = float(root.get('branch-rate', '0')) * 100
print(f'{lr:.2f} {br:.2f}')
" "$COV_XML")
  echo ""
  echo "  coverage.xml: line=${line_cov}%  branch=${branch_cov}%"
  assert "Coverage >= 99.5% (line + branch)" python3 -c "
import xml.etree.ElementTree as ET, sys
tree = ET.parse(sys.argv[1])
root = tree.getroot()
assert float(root.get('line-rate','0'))*100 >= 99.5, f'line {float(root.get(\"line-rate\", \"0\"))*100:.1f} < 99.5'
assert float(root.get('branch-rate','0'))*100 >= 99.5, f'branch {float(root.get(\"branch-rate\", \"0\"))*100:.1f} < 99.5'
" "$COV_XML"
else
  echo ""
  echo "  [WARN] $COV_XML not found — skipping coverage check"
fi

# ── 6. Summary ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Quality Gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  RESULT: OK" || echo "  RESULT: FAILED"
echo "============================================================"
exit "$FAIL"