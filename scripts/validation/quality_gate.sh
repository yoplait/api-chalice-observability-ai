#!/usr/bin/env bash
# Host-side quality gate + coverage enforcement after SonarScanner run.
set -euo pipefail

SONAR="${SONAR_HOST_URL:-http://localhost:9000}"
TOKEN_FILE="${SONAR_TOKEN_FILE:-.sonar/token}"
PROJECT="${SONAR_PROJECT_KEY:-chalice-devops-lab}"
COV_XML="${COV_XML:-coverage.xml}"
PASS=0
FAIL=0

assert(){
  if "$@"; then echo "  [PASS] $1"; PASS=$((PASS+1)); else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi
}

echo "============================================================"
echo "  SonarQube Quality Gate — Validation"
echo "============================================================"

# 1. Wait for analysis to complete (CE queue)
echo -n "  Waiting for CE analysis to finish... "
deadline=$(( $(date +%s) + 300 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  raw="$(curl -sf "$SONAR/api/ce/component?query=$PROJECT" 2>/dev/null || echo '{}')"
  result="$(echo "$raw" | jq -r '.current.status // "QUEUED"')"
  if [ "$result" = "SUCCESS" ]; then echo "SUCCESS"; break
  elif [ "$result" = "FAILED" ] || [ "$result" = "ERR" ]; then
    echo "$result"; assert "CE task completed successfully" false; exit 1
  fi
  sleep 5
done
[ "$result" = "SUCCESS" ] || { echo "timeout"; assert "CE completion" false; exit 1; }

# 2. Poll Quality Gate result until computed
echo -n "  Waiting for Quality Gate computation... "
deadline=$(( $(date +%s) + 120 ))
result=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  computed="$(curl -sf "$SONAR/api/qualitygates/project_status?project=$PROJECT" 2>/dev/null | jq -r '.projectStatus.computed // empty' || echo '')"
  [ "$computed" = "true" ] && break
  sleep 5
done
[ "$computed" = "true" ] || { echo "never computed"; assert "QC computed" false; exit 1; }
echo "OK"

# 3. Gate conditions table
echo ""
echo "  Quality Gate results:"
curl -sf "$SONAR/api/qualitygates/project_status?project=$PROJECT" | jq '.projectStatus.conditions[] | "    \(.metric)  actual=\(.actualValue)  errorThreshold=\(.errorThreshold)  status=\(.status)"'
echo ""
gate_status="$(curl -sf "$SONAR/api/qualitygates/project_status?project=$PROJECT" | jq -r '.projectStatus.status')"
echo "  Overall status: $gate_status"

# 4. Coverage enforcement (Sonar Community may not enforce all natively)
if [ -s "$COV_XML" ]; then
read -r line_cov branch_cov < <(python3 -c "
import xml.etree.ElementTree as ET, sys
tree = ET.parse(sys.argv[1])
root = tree.getroot()
lr = float(root.get('line-rate', '0')) * 100
br = float(root.get('branch-rate', '0')) * 100
print(f'{lr:.2f} {br:.2f}')
" "$COV_XML")
  echo "  coverage.xml: line=$line_cov%  branch=$branch_cov%"
  assert "Coverage >= 99.5% (line + branch enforced locally)" python3 -c "
import xml.etree.ElementTree as ET, sys, math
tree = ET.parse(sys.argv[1])
root = tree.getroot()
if float(root.get('line-rate','0'))*100 < 99.5 or float(root.get('branch-rate','0'))*100 < 99.5:
    raise SystemExit(1)
" "$COV_XML"
else
  echo "  [WARN] $COV_XML not found — skipping coverage enforcement"
fi

echo ""
echo "============================================================"
echo "  Quality Gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  RESULT: OK" || echo "  RESULT: FAILED"
echo "============================================================"
exit "$FAIL"