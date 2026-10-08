#!/usr/bin/env bash
# Helper for Make bootstrap: start monitoring stack and wait.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose up -d prometheus blackbox-exporter grafana 2>/dev/null || true
echo "  [MONITORING] containers started, waiting for healthchecks..."
deadline=$(( $(date +%s) + 60 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -sf http://localhost:9090/-/ready >/dev/null 2>&1; then
    echo "  [MONITORING] Prometheus ready"; break
  fi
  sleep 3
done