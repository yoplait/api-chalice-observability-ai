#!/usr/bin/env bash
# Helper for Make bootstrap: quick pre-check before running full E2E.
set -euo pipefail
if curl -sf http://localhost:9115/-/healthy >/dev/null 2>&1; then echo "  [MONITORING] Blackbox healthy"; fi
if curl -sf http://localhost:9090/-/ready >/dev/null 2>&1; then echo "  [MONITORING] Prometheus healthy"; fi
if curl -sf http://localhost:3000/api/health >/dev/null 2>&1; then echo "  [MONITORING] Grafana healthy"; fi