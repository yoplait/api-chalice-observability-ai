# The Lambda metrics path — plain English

## The problem

When you run `make start` locally, your API lives in one process that stays
running. A program called **Prometheus** comes to its `/metrics` page every 15
seconds, counts things, and Grafana draws the graphs. Easy.

**AWS Lambda is different.** Lambda does not keep a process alive. Each time
someone hits the API, Lambda spins up a tiny container, runs the code, sends
the answer back, and **kills the container**. The next hit might get a new
container. There is no process to scrape and no `/metrics` page anyone can
reach.

So the local metrics model (count in memory, scrape from outside) does not work.

## The solution: push instead of pull

Instead of accumulating counts in a local container and hoping someone scrapes
you, **each request pushes its own number to CloudWatch** (AWS's metrics
system). CloudWatch does the counting for you — it sums, averages and
percentiles across all concurrent executions. You no longer need a scrapable
endpoint.

## How the code works (one sentence each)

1. **Collect:** the middleware already times every request (this is the same
   code, local or Lambda).
2. **Store locally:** `REGISTRY` increments counters in memory — same as now.
3. **Store in Lambda:** if the env var `METRICS_BACKEND=cloudwatch` is set, an
   additional call writes the same numbers to CloudWatch via **EMF** (Embedded
   Metric Format) using a library called **AWS Lambda Powertools**.
4. **Expose:** on Lambda, the `/metrics` route is disabled (`METRICS_ENABLED:
   false`) — not because metrics don't work, but because CloudWatch is the
   source of truth now. On local, `/metrics` still works exactly as before.

## Why it does not break tests

The CloudWatch code is imported *only when* `METRICS_BACKEND=cloudwatch`. Locally
(default `inproc`) it is never executed. Tests use a fake "sink" (a simple
list) instead of the AWS SDK, so **no AWS library is required** and coverage
stays at 100%. The local tests that assert `REGISTRY` increments are unaffected.

## How to deploy

```bash
make deploy        # quality gate → chalice package → chalice deploy
```

That runs `scripts/deploy_lambda.sh` which:
1. Checks the SonarQube quality gate locally (if the stack is running; CI enforces it otherwise).
2. Packages with Chalice (`prod` stage: `METRICS_BACKEND=cloudwatch`).
3. Deploys to API Gateway + Lambda.

The Lambda function needs one extra IAM permission: `cloudwatch:PutMetricData`
scoped to our namespace. The `policy-prod.json` file already has it.

## Where to see the numbers

**CloudWatch (free, no setup):**
```bash
aws cloudwatch list-metrics --namespace ChaliceLab
```
or build a dashboard in the CloudWatch console.

**Grafana:** Grafana connects natively to CloudWatch. Just point it at `ChaliceLab`.

**Keep Prometheus too:** run `prometheus-cloudwatch-exporter` on a small
container. It pulls from CloudWatch and re-exposes `/metrics` so your existing
Prometheus scrapes it and Grafana plots it. This preserves your current
dashboards.

**Free bonus:** even without EMF, API Gateway and Lambda emit their own metrics
(`Count`, `Latency`, `Errors`, `Invocations`) automatically. Use them for basic
SRE.

## SonarQube is separate

SonarQube does **code quality** in CI (GitHub Actions or local). It is not a
runtime dependency of the Lambda function. The metrics pipeline (CloudWatch vs
Prometheus) has nothing to do with Sonar. CI scans the code; Lambda pushes
metrics. Two independent pipelines.