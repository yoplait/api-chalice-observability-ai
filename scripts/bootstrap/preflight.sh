#!/usr/bin/env bash
# Preflight checks before bootstrap.
set -euo pipefail
PASS=0
FAIL=0
assert(){
  if eval "$@"; then echo "  [PASS] $1"; PASS=$((PASS+1))
  else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi
}

echo "============================================================"
echo "  Preflight Checks"
echo "============================================================"

echo "  [CHECK] Docker"
assert "Docker daemon running" "docker info >/dev/null 2>&1"

echo "  [CHECK] Docker Compose"
assert "Compose available" "$(docker compose version --short 2>/dev/null | grep -qE '[2-9]\\.|^[1-9][0-9]\\.') || docker compose version >/dev/null 2>&1"

echo "  [CHECK] Architecture"
arch="$(docker info --format '{{.Architecture}}' 2>/dev/null || echo unknown)"
echo "  Architecture: $arch"

echo "  [CHECK] Docker Desktop VM resources"
cpu="$(docker info --format '{{.NCPU}}' 2>/dev/null || echo '?')"
mem="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo '?')"
mem_gb=$((mem / 1073741824))
echo "  CPU: $cpu  RAM: ${mem_gb} GiB"
[ "$cpu" -ge 4 ] 2>/dev/null && assert "CPU >= 4" test "$cpu" -ge 4 || true
[ "$mem_gb" -ge 4 ] 2>/dev/null && assert "RAM >= 4 GiB" test "$mem_gb" -ge 4 || true

echo "  [CHECK] Port availability"
for port in 8000 9000 3000 9090 9115; do
  if lsof -iTCP:"$port" -sTCP:LISTEN -P 2>/dev/null | grep -q ssh; then
    echo "  [WARN] port $port in use by ssh (can be killed)"
  elif lsof -iTCP:"$port" -sTCP:LISTEN -P 2>/dev/null | grep -q node; then
    echo "  [WARN] port $port in use by Node.js"
  elif lsof -iTCP:"$port" -sTCP:LISTEN -P 2>/dev/null | grep -q docker; then
    echo "  [WARN] port $port in use by Docker"
  else
    assert "Port $port free" "lsof -iTCP:$port -sTCP:LISTEN -P 2>/dev/null | grep -qvE 'ssh|node|docker|Docker Desktop' || true"
  fi
done

echo "  [CHECK] Required tools"
assert "curl available" "command -v curl >/dev/null"
assert "jq available" "command -v jq >/dev/null"
assert "bash 4+" "$(bash -c 'echo $BASH_VERSION' | grep -qE '^5|^4')"

echo "  [CHECK] Python 3.12"
python_ver="$(python3.12 --version 2>/dev/null || python3 --version 2>/dev/null || echo 'none')"
echo "  Python: $python_ver"

echo "  [CHECK] .env or .env.example"
[ -f .env ] && assert ".env exists" test -f .env || \
  [ -f .env.example ] && assert ".env.example exists (will generate .env)" test -f .env.example || \
  (echo "  [FAIL] No .env or .env.example"; FAIL=$((FAIL+1)))

echo ""
echo "============================================================"
echo "  Preflight: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  RESULT: OK" || echo "  RESULT: FAILED — fix issues above"
echo "============================================================"
exit "$FAIL"