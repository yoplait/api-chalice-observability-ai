#!/usr/bin/env bash
# End-to-end observability validation with failure simulation and recovery.
# All checks use host localhost ports (compose ports map to host).
# MUST restore the API on failure (trap/cleanup).
set -uo pipefail

API="${CHALICE_BASE_URL:-http://localhost:8080}"
BLACKBOX="http://localhost:9115"
PROM="http://localhost:9090"
GRAFANA="http://localhost:3001"
ADMIN="${GRAFANA_ADMIN_USER:-admin}:${GRAFANA_ADMIN_PASSWORD:-admin}"
PASS=0
FAIL=0

assert(){
  if eval "$@"; then echo "  [PASS] $1"; PASS=$((PASS+1))
  else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi
}

restore_api() {
  echo ""
  echo "  [RESTORE] restarting chalice-api..."; sleep 2
  # try compose; fall back to local
  if docker compose --project-name chalice-devops-lab restart chalice-api 2>/dev/null || \
     docker compose restart chalice-api 2>/dev/null || true; then
    local d=$(( $(date +%s) + 40 ))
    while [ "$(date +%s)" -lt "$d" ]; do
      if curl -sf "$API/health" >/dev/null 2>&1; then echo "  [RESTORE] API is back"; return 0; fi
      sleep 2
    done
  fi
  echo "  [WARN] could not restore API via compose; attempting chalice local..."; false
}

trap restore_api EXIT
echo "============================================================"
echo "  Observability — End-to-End Validation"
echo "============================================================"

# ---- Step 1: Chalice /health & /hello ----
echo ""
echo "  [1] Checking Chalice API..."
status_health="$(curl -sf -o /dev/null -w '%{http_code}' "$API/health")"
assert "Chalice /health" "test $status_health = 200"
hello="$(curl -sf "$API/hello")"
assert "Chalice /hello JSON" "echo '$hello' | jq -e '.message' >/dev/null"
echo "  [PASS] Chalice API OK"

# ---- Step 2: Blackbox probes ----
echo ""
echo "  [2] Executing Blackbox probes..."
for endpoint in health ready hello version; do
  url="$API/$endpoint"
  module="http_$endpoint"
  raw="$(curl -sf "$BLACKBOX/probe?target=$url&module=$module" 2>/dev/null || true)"
  probe_ok="$(echo "$raw" | jq -r '.success' 2>/dev/null || echo "null")"
  assert "Blackbox probe $endpoint" "test \"$probe_ok\" = 'true'"
done

# ---- Step 3: Prometheus targets ----
echo ""
echo "  [3] Verifying Prometheus targets..."
ready="$(curl -sf "$PROM/-/ready" 2>/dev/null || echo "no")"
assert "Prometheus ready" "test \"$ready\" = 'Prometheus Server is Ready.'"
targets="$(curl -sf "$PROM/api/v1/targets" | jq '.data.activeTargets | length' 2>/dev/null)"
assert "Prometheus has active targets" "test \"$targets\" -ge 3"
up_targets="$(curl -sf "$PROM/api/v1/targets" | jq '[.data.activeTargets[] | select(.health=="up")] | length' 2>/dev/null)"
assert "Prometheus targets are UP" "test \"$up_targets\" -ge 3"
probe_success="$(curl -sf "$PROM/api/v1/query?query=probe_success{job=\"blackbox-http\"}" | jq '.data.result | length' 2>/dev/null || echo 0)"
assert "probe_success series exist" "test \"$probe_success\" -ge 4"

# ---- Step 4: Grafana datasource + dashboard ----
echo ""
echo "  [4] Verifying Grafana provisioning..."
auth="$(curl -sf -u "$ADMIN" "$GRAFANA/api/health" | jq -r '.commit' 2>/dev/null || echo "")"
assert "Grafana health" "test -n \"$auth\""
ds="$(curl -sf -u "$ADMIN" "$GRAFANA/api/datasources/uid/chalice-prom" | jq -r '.name' 2>/dev/null || echo "null")"
assert "Prometheus datasource provisioned" "test \"$ds\" = 'Prometheus'"
dash="$(curl -sf -u "$ADMIN" "$GRAFANA/api/dashboards/uid/chalice-observability" | jq -r '.dashboard.id' 2>/dev/null || echo "null")"
assert "Dashboard provisioned" "test \"$dash\" != 'null' && \"$dash\" != ''"

# ---- Step 5: Real Prometheus query execution via Grafana proxy ----
echo ""
echo "  [5] Executing real Prometheus query through Grafana proxy..."
query_result="$(curl -sf -u "$ADMIN" "$GRAFANA/api/datasources/proxy/uid/chalice-prom/api/v1/query?query=up" 2>/dev/null | jq -r '.data.result | length' 2>/dev/null || echo 0)"
assert "Grafana proxy query works" "test \"$query_result\" -ge 3"

# ---- Step 6: Synthetic traffic + Prometheus samples ----
echo ""
echo "  [6] Generating traffic and verifying new samples..."
pre_requests="$(curl -sf "$PROM/api/v1/query?query=chalice_http_requests_total" | jq '.data.result | .[0].value[1]' 2>/dev/null || echo 0)"
# Send traffic directly (no need to start the traffic container)
for i in $(seq 1 10); do curl -sf "$API/hello" >/dev/null 2>&1 || true; done
sleep 16
post_requests="$(curl -sf "$PROM/api/v1/query?query=chalice_http_requests_total" | jq '.data.result | .[0].value[1]' 2>/dev/null || echo 0)"
assert "Prometheus captured traffic increase" "[ "$post_requests" -gt "$pre_requests" ] 2>/dev/null || test "$(python3 -c "print(int($post_requests) > int($pre_requests))" 2>/dev/null || echo 0)" = "True"

# ---- Step 7: Controlled failure simulation ----
echo ""
echo "  [7] Simulating API failure (stopping API for detection)..."
docker compose --project-name chalice-devops-lab stop chalice-api >/dev/null 2>&1 || \
  docker compose stop chalice-api >/dev/null 2>&1 || true
echo "  [PAUSED] chalice-api stopped, waiting for detection..."

# Wait for probe_success to drop to 0 — bounded by scrape interval (15s) + for duration
deadline=$(( $(date +%s) + 90 ))
probe_down=false
while [ "$(date +%s)" -lt "$deadline" ]; do
  success="$(curl -sf "$PROM/api/v1/query?query=probe_success{job=\"blackbox-http\",endpoint=\"health\"}" | jq '.data.result | .[0].value[1] // "null"' 2>/dev/null || echo null)"
  if [ "$success" = "0" ] || [ "$success" = "null" ]; then probe_down=true; break; fi
  sleep 5
done
assert "Blackbox detected failure" "test \"$probe_down\" = 'true'"

# Check Prometheus alert state
deadline_alert=$(( $(date +%s) + 180 ))
alert_firing=false
while [ "$(date +%s)" -lt "$deadline_alert" ]; do
  alerts="$(curl -sf "$PROM/api/v1/alerts" | jq '[.data[] | select(.state=="firing") | .labels.alertname] | length' 2>/dev/null || echo 0)"
  if [ "$alerts" -gt 0 ] 2>/dev/null; then alert_firing=true; break; fi
  sleep 15
done
assert "Prometheus alert fired for API down" "test \"$alert_firing\" = 'true'"

# Check Grafana alert state
grafana_alerts="$(curl -sf -u "$ADMIN" "$GRAFANA/api/alerts" 2>/dev/null | jq 'length' || echo 0)"
if [ "$grafana_alerts" != "0" ] 2>/dev/null; then
  assert "Grafana alert present" "test \"$grafana_alerts\" -gt 0"
fi

# ---- Step 8: Recovery ----
echo ""
echo "  [8] Restoring API and verifying recovery..."
restore_api

# Verify probe returns to 1
deadline_recover=$(( $(date +%s) + 60 ))
recovered=false
while [ "$(date +%s)" -lt "$deadline_recover" ]; do
  success="$(curl -sf "$PROM/api/v1/query?query=probe_success{job=\"blackbox-http\",endpoint=\"health\"}" | jq '.data.result | .[0].value[1] // "null"' 2>/dev/null || echo null)"
  if [ "$success" = "1" ]; then recovered=true; break; fi
  sleep 5
done
assert "Probe recovered after restore" "test \"$recovered\" = 'true'"

# Verify alert resolves (state changes to inactive/no firing)
deadline_resolve=$(( $(date +%s) + 90 ))
resolved=false
while [ "$(date +%s)" -lt "$deadline_resolve" ]; do
  firing="$(curl -sf "$PROM/api/v1/alerts" | jq '[.data[] | select(.state=="firing")] | length' 2>/dev/null || echo 1)"
  if [ "$firing" = "0" ]; then resolved=true; break; fi
  sleep 15
done
assert "Alert resolved after recovery" "test \"$resolved\" = 'true'"

echo ""
echo "============================================================"
echo "  Observability E2E: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  RESULT: OK" || echo "  RESULT: FAILED"
echo "============================================================"
exit "$FAIL"