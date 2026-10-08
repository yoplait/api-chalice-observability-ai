#!/usr/bin/env bash
# Smoke tests against the live Chalice API on localhost.
set -euo pipefail
BASE="${CHALICE_BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0
assert(){
  local desc="$1" status="$2"; shift 2
  if eval "$@"; then
    echo "  [PASS] $desc (HTTP $status)"
    PASS=$((PASS+1))
  else
    echo "  [FAIL] $desc (HTTP $status)"
    FAIL=$((FAIL+1))
  fi
}

echo "============================================================"
echo "  Chalice API — Smoke Tests"
echo "============================================================"

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/")"
assert "Index" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/hello")"
assert "Hello default" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/hello?name=Smoke")"
assert "Hello named" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/health")"
assert "Health" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/ready")"
assert "Readiness" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/version")"
assert "Version" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/metrics")"
assert "Metrics" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/greet/alice")"
assert "Greet" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/demo/error?kind=bad_request")"
assert "Demo bad_request" "$r_status" test "$r_status" = 400

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/demo/error?kind=unavailable")"
assert "Demo unavailable" "$r_status" test "$r_status" = 503

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/demo/exception")"
assert "Demo exception" "$r_status" test "$r_status" = 500

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/demo/slow?delay=0.05")"
assert "Demo slow (fast)" "$r_status" test "$r_status" = 200

r_status="$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/demo/slow?delay=99")"
assert "Demo slow (out of range)" "$r_status" test "$r_status" = 400

echo ""
echo "============================================================"
echo "  Smoke: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  RESULT: OK" || echo "  RESULT: FAILED"
echo "============================================================"
exit "$FAIL"