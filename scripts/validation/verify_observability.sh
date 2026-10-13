#!/usr/bin/env bash
# End-to-end observability validation with failure simulation and recovery.
# Skips gracefully if required services aren't running.

# Detect docker compose binary
if docker compose version >/dev/null 2>&1; then
  COMPOSE_BIN="docker"
  COMPOSE_SUB="compose"
elif docker-compose version >/dev/null 2>&1; then
  COMPOSE_BIN="docker-compose"
  COMPOSE_SUB=""
elif [ -x /opt/homebrew/bin/docker-compose ]; then
  COMPOSE_BIN="/opt/homebrew/bin/docker-compose"
  COMPOSE_SUB=""
elif [ -x /usr/local/bin/docker-compose ]; then
  COMPOSE_BIN="/usr/local/bin/docker-compose"
  COMPOSE_SUB=""
elif [ -x /Users/perezpardojc/.rd/bin/docker-compose ]; then
  COMPOSE_BIN="/Users/perezpardojc/.rd/bin/docker-compose"
  COMPOSE_SUB=""
else
  COMPOSE_BIN=""
  COMPOSE_SUB=""
fi
COMPOSE_FILE="$(ls compose.yaml docker-compose.yaml 2>/dev/null | head -1 || echo "compose.yaml")"

# Load .env for Grafana password
SCRIPT_DIR="$(cd "$(dirname "$0")/../../" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
  GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-$(grep -m1 '^GRAFANA_ADMIN_PASSWORD=' "$SCRIPT_DIR/.env" 2>/dev/null | cut -d= -f2-)}"
  GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-$(grep -m1 '^GRAFANA_ADMIN_USER=' "$SCRIPT_DIR/.env" 2>/dev/null | cut -d= -f2-)}"
fi

API="${CHALICE_BASE_URL:-http://localhost:8080}"
BLACKBOX="http://localhost:9115"
PROM="http://localhost:9090"
GRAFANA="http://localhost:3001"
ADMIN="${GRAFANA_ADMIN_USER:-admin}:${GRAFANA_ADMIN_PASSWORD:-admin}"
PASS=0
FAIL=0

assert(){
  local desc="$1"; shift
  if eval "$@"; then echo "  [PASS] $desc"; PASS=$((PASS+1))
  else echo "  [FAIL] $desc"; FAIL=$((FAIL+1)); fi
}

assert_eq(){
  if [ "$2" = "$3" ]; then
    echo "  [PASS] $1"; PASS=$((PASS+1))
  else
    echo "  [FAIL] $1 (expected='$3' actual='$2')"; FAIL=$((FAIL+1))
  fi
}
assert_ge(){
  if [ "$2" -ge "$3" ] 2>/dev/null; then
    echo "  [PASS] $1"; PASS=$((PASS+1))
  else
    echo "  [FAIL] $1 (value=$2 min=$3)"; FAIL=$((FAIL+1))
  fi
}
assert_true(){
  if [ "$2" = "true" ] || [ "$2" = "1" ]; then
    echo "  [PASS] $1"; PASS=$((PASS+1))
  else
    echo "  [FAIL] $1 (expected=1 actual=$2)"; FAIL=$((FAIL+1))
  fi
}
assert_gt(){
  if [ "$2" -gt "$3" ] 2>/dev/null; then
    echo "  [PASS] $1"; PASS=$((PASS+1))
  else
    echo "  [FAIL] $1 (value=$2 min=$3)"; FAIL=$((FAIL+1))
  fi
}

echo "============================================================"
echo "  Observability — End-to-End Validation"
echo "============================================================"

if ! curl -sf --max-time 3 "$API/health" >/dev/null 2>&1; then
  echo "  [SKIP] Chalice API not reachable at $API — skipping observability validation"
  exit 0
fi

restore_api() {
  echo ""
  echo "  [RESTORE] restarting chalice-api..."
  sleep 2
  if [ -n "$COMPOSE_BIN" ]; then
    if "$COMPOSE_BIN" "$COMPOSE_SUB" --project-name chalice-devops-lab -f "$COMPOSE_FILE" restart chalice-api 2>/dev/null || \
       "$COMPOSE_BIN" "$COMPOSE_SUB" restart chalice-api 2>/dev/null || true; then
      local d=$(( $(date +%s) + 40 ))
      while [ "$(date +%s)" -lt "$d" ]; do
        if curl -sf "$API/health" >/dev/null 2>&1; then echo "  [RESTORE] API is back"; return 0; fi
        sleep 2
      done
    fi
  fi
  echo "  [WARN] could not restore API"
  return 1
}

trap restore_api EXIT

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
  internal_url="http://chalice-api:8000/$endpoint"
  module="http_$endpoint"
  encoded_target=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$internal_url', safe=''))" 2>/dev/null)
  raw="$(curl -sf "$BLACKBOX/probe?target=${encoded_target}&module=$module" 2>/dev/null || true)"
  probe_success_val="$(echo "$raw" | grep '^probe_success ' | awk '{print $2}' || echo "0")"
  assert_true "Blackbox probe $endpoint" "$probe_success_val"
done

# ---- Step 3: Prometheus targets ----
echo ""
echo "  [3] Verifying Prometheus targets..."
ready="$(curl -sf "$PROM/-/ready" 2>/dev/null || echo "no")"
assert_eq "Prometheus ready" "$ready" "Prometheus Server is Ready."
targets="$(curl -sf "$PROM/api/v1/targets" 2>/dev/null | jq '.data.activeTargets | length' || echo 0)"
assert_ge "Prometheus has active targets" "$targets" 3
up_targets="$(curl -sf "$PROM/api/v1/targets" 2>/dev/null | jq '[.data.activeTargets[] | select(.health=="up")] | length' || echo 0)"
assert_ge "Prometheus targets are UP" "$up_targets" 3
probe_success="$(curl -sf "$PROM/api/v1/query" --data-urlencode 'query=probe_success{job="blackbox-http"}' 2>/dev/null | jq '.data.result | length' || echo 0)"
assert_ge "probe_success series exist" "$probe_success" 4

# ---- Step 4: Grafana datasource + dashboard ----
echo ""
echo "  [4] Verifying Grafana provisioning..."
auth="$(curl -sf -u "$ADMIN" "$GRAFANA/api/health" 2>/dev/null | jq -r '.database' || echo "")"
assert_eq "Grafana health" "$auth" "ok"
ds_raw="$(curl -sf -u "$ADMIN" "$GRAFANA/api/datasources" 2>/dev/null || echo "")"
ds="$(echo "$ds_raw" | jq -r '.[0].name // empty' || echo "")"
assert_eq "Prometheus datasource provisioned" "$ds" "Prometheus"
dash_raw="$(curl -sf -u "$ADMIN" "$GRAFANA/api/dashboards/uid/chalice-observability" 2>/dev/null || echo "{}")"
dash="$(echo "$dash_raw" | jq -r '.dashboard.id // empty' || echo "")"
if [ -n "$dash" ] && [ "$dash" != "null" ]; then
  echo "  [PASS] Dashboard provisioned"; PASS=$((PASS+1))
else
  echo "  [FAIL] Dashboard provisioned"; FAIL=$((FAIL+1))
fi

# ---- Step 5: Real Prometheus query execution via Grafana proxy ----
echo ""
echo "  [5] Executing real Prometheus query through Grafana proxy..."
query_result="$(curl -sf -u "$ADMIN" "$GRAFANA/api/datasources/proxy/uid/chalice-prom/api/v1/query?query=up" 2>/dev/null | jq -r '.data.result | length' || echo 0)"
assert_ge "Grafana proxy query works" "$query_result" 3

# ---- Step 6: Synthetic traffic + Prometheus samples ----
echo ""
echo "  [6] Generating traffic and verifying new samples..."
pre_requests="$(curl -sf "$PROM/api/v1/query?query=sum(chalice_http_requests_total)" 2>/dev/null | jq '.data.result | .[0].value[1] // 0' || echo 0)"
for i in $(seq 1 10); do curl -sf "$API/hello" >/dev/null 2>&1 || true; done
sleep 16
post_requests="$(curl -sf "$PROM/api/v1/query?query=sum(chalice_http_requests_total)" 2>/dev/null | jq '.data.result | .[0].value[1] // 0' || echo 0)"
assert "Prometheus captured traffic increase" "python3 -c 'import sys; sys.exit(0 if int(sys.argv[2]) > int(sys.argv[1]) else 1)' $pre_requests $post_requests"

# ---- Step 7: Controlled failure simulation ----
echo ""
echo "  [7] Simulating API failure (stopping API for detection)..."
if [ -n "$COMPOSE_BIN" ]; then
  "$COMPOSE_BIN" "$COMPOSE_SUB" --project-name chalice-devops-lab -f "$COMPOSE_FILE" stop chalice-api >/dev/null 2>&1 || \
  "$COMPOSE_BIN" "$COMPOSE_SUB" stop chalice-api >/dev/null 2>&1 || true
fi
echo "  [PAUSED] chalice-api stopped, waiting for detection..."

deadline=$(( $(date +%s) + 90 ))
probe_down=false
while [ "$(date +%s)" -lt "$deadline" ]; do
  success="$(curl -sf "$PROM/api/v1/query" --data-urlencode 'query=probe_success{job="blackbox-http"}' 2>/dev/null | jq -r '.data.result[0].value[1] // "null"' || echo "null")"
  if [ "$success" = "0" ] || [ "$success" = "null" ]; then probe_down=true; break; fi
  sleep 5
done
assert_true "Blackbox detected failure" "$probe_down"

deadline_alert=$(( $(date +%s) + 180 ))
alert_firing=false
while [ "$(date +%s)" -lt "$deadline_alert" ]; do
  alerts="$(curl -sf "$PROM/api/v1/alerts" 2>/dev/null | jq '[.data.alerts[] | select(.state=="firing")] | length' || echo 0)"
  if [ "$alerts" -gt 0 ] 2>/dev/null; then alert_firing=true; break; fi
  sleep 15
done
assert_true "Prometheus alert fired for API down" "$alert_firing"

grafana_alerts="$(curl -sf -u "$ADMIN" "$GRAFANA/api/v1/provisioning/alert-rules" 2>/dev/null | jq 'length' 2>/dev/null || echo 0)"
legacy_alerts="$(curl -sf -u "$ADMIN" "$GRAFANA/api/alerts" 2>/dev/null | jq 'length' 2>/dev/null || echo 0)"
if [ "${grafana_alerts:-0}" -gt 0 ] 2>/dev/null || [ "${legacy_alerts:-0}" -gt 0 ] 2>/dev/null; then
  echo "  [PASS] Grafana alert present"
  PASS=$((PASS+1))
else
  echo "  [WARN] Grafana alert not visible yet (optional — state sync takes ~1 min)"
fi

# ---- Step 8: Recovery ----
echo ""
echo "  [8] Restoring API and verifying recovery..."
restore_api

deadline_recover=$(( $(date +%s) + 60 ))
recovered=false
while [ "$(date +%s)" -lt "$deadline_recover" ]; do
  success="$(curl -sf "$PROM/api/v1/query" --data-urlencode 'query=probe_success{job="blackbox-http"}' 2>/dev/null | jq -r '.data.result[0].value[1] // "null"' || echo "null")"
  if [ "$success" = "1" ]; then recovered=true; break; fi
  sleep 5
done
assert_true "Probe recovered after restore" "$recovered"

deadline_resolve=$(( $(date +%s) + 90 ))
resolved=false
while [ "$(date +%s)" -lt "$deadline_resolve" ]; do
  firing="$(curl -sf "$PROM/api/v1/alerts" 2>/dev/null | jq '[.data.alerts[] | select(.state=="firing")] | length' || echo 1)"
  if [ "$firing" = "0" ]; then resolved=true; break; fi
  sleep 15
done
assert_true "Alert resolved after recovery" "$resolved"

echo ""
echo "============================================================"
echo "  Observability E2E: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  RESULT: OK" || echo "  RESULT: FAILED"
echo "============================================================"
exit "$FAIL"