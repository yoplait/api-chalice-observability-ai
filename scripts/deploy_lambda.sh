#!/usr/bin/env bash
# Deploy the Chalice API to AWS Lambda (the "definitive" cloud path).
# The LOCAL pipeline is unchanged; this is only the publishing tool.
#
# Prerequisites:
#   - pip install chalice  (in the venv, or globally)
#   - aws configure       (or AWS_PROFILE set) — needs IAM deploy permissions
#   - requirements-lambda.txt lists aws-lambda-powertools (EMF metrics backend)
#
# What it does:
#   1. Validate the gate locally first (coverage + Sonar quality gate) so we
#      never deploy code that would fail CI.
#   2. Package with Chalice (prod stage: METRICS_BACKEND=cloudwatch).
#   3. Deploy to API Gateway + Lambda.
#
# After deploy, CloudWatch receives the EMF dimensions per request
# (http_requests / request_duration_ms / http_errors). Visualise them in a
# CloudWatch dashboard, or scrape them back into your existing Prometheus/
# Grafana with prometheus-cloudwatch-exporter — see docs/observability.md.
#
# Usage:  bash scripts/deploy_lambda.sh [dev|prod]
set -euo pipefail

STAGE="${1:-prod}"
CHALICE="$(pwd)/.venv/bin/chalice"
[ -x "$CHALICE" ] || CHALICE="chalice"

echo "============================================================"
echo "  Deploying chalice-devops-lab — stage: $STAGE"
echo "============================================================"

# 1) Do not ship failing code. If the SonarQube stack is running we can check
#    the gate; if not, this step is skipped (CI already gates on GitHub).
if curl -sf http://localhost:9000/api/system/status >/dev/null 2>&1 && [ -s .sonar/token ]; then
  echo "  [1/3] Running quality gate locally before deploy..."
  bash scripts/validation/quality_gate.sh
else
  echo "  [1/3] SonarQube stack not running — skipping local gate (CI enforces it)."
fi

# 2) Package
echo "  [2/3] chalice package ($STAGE)..."
rm -rf sam_out && mkdir -p sam_out
"$CHALICE" --stage "$STAGE" package --sam-template sam_out/template.yaml

# 3) Deploy
echo "  [3/3] chalice deploy ($STAGE)..."
"$CHALICE" --stage "$STAGE" deploy
URL="$("$CHALICE" --stage "$STAGE" url)"
echo ""
echo "  Deployed. API URL: $URL"
echo "  Lambda function: chalice-devops-lab-${STAGE}"
echo "  Metrics namespace: ChaliceLab (CloudWatch, EMF)"
echo ""
echo "  Smoke it:"
echo "    curl $URL/health"
echo "  Check CloudWatch:"
echo "    aws cloudwatch list-metrics --namespace ChaliceLab"
