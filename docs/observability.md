# Observability: metrics on local (Prometheus) vs AWS Lambda (CloudWatch)

Chalice is designed to deploy to **AWS Lambda**. The metrics model that works
locally does **not** work unchanged on Lambda. This document is the definitive
guide to both: how metrics are collected, stored and exposed locally, and what
changes for a real Lambda deployment — **without breaking the local test model**.

> TL;DR: local = **pull** (Prometheus scrapes `/metrics`). Lambda = **push**
> (each request emits to CloudWatch via EMF). The code supports both; the
> backend is selected by `METRICS_BACKEND` (`inproc` locally, `cloudwatch` on
> Lambda). The local path is the default and is completely unchanged.

---

## 1. How metrics are collected, stored and exposed (the local model)

Three files implement the whole in-process pipeline.

### 1.1 Collected — `chalicelib/observability/pipeline.py`
A Chalice HTTP middleware wraps **every** request. In its `finally` block (so it
records even failures) it times the request and reads the status code:

```python
started  = time.perf_counter()
response = get_response(request)
duration = time.perf_counter() - started
status   = int(getattr(response, "status_code", 500))
route    = getattr(request, "path", "") or "/"
REGISTRY.observe_request(route, method, status, duration)   # <-- always runs
```

This is how we "know how many requests hit the API": every request calls
`observe_request`.

### 1.2 Stored — `chalicelib/observability/metrics.py`
Counters live **in the memory of the process** (no database). The registry
holds a `Counter` for request counts, a `Histogram` for latency, and a
`Counter` for 5xx errors, keyed by labels (`route`, `method`, `status`):

```python
def observe_request(self, route, method, status, duration):
    status_class = f"{status // 100}xx"            # 200->2xx, 503->5xx
    self.requests_total.inc((route, method, status_class))  # dict[labels] += 1
    self.request_duration.observe((route, method), duration)
    if status >= 500:
        self.errors_total.inc((route,))
```

One number per label-combination, not one row per request. `threading.Lock`
makes it concurrency-safe.

### 1.3 Exposed — `chalicelib/handlers/core.py`
`GET /metrics` serialises the registry into the **Prometheus text format** and
serves it with `Content-Type: text/plain`:

```python
@core_routes.route("/metrics", methods=["GET"])
def metrics():
    if not cfg.metrics_enabled:
        raise ResourceNotFound(...)              # route can be turned off
    return Response(body=REGISTRY.render(), status_code=200,
                    headers={"Content-Type": "text/plain; version=0.0.4"})
```

`render()` emits lines like:

```
# TYPE chalice_http_requests_total counter
chalice_http_requests_total{route="/hello",method="GET",status="2xx"} 1027
```

### 1.4 Then the stack does its part
`prometheus.yml` scrapes `chalice-api:8000/metrics` every 15s; Prometheus
stores the time series; Grafana plots them. That is the pull pipeline and the
one your tests (`make validate`, the blackbox + observability E2E) exercise.

---

## 2. Why the local model breaks on AWS Lambda

| Local assumption | Reality on Lambda | Consequence |
|------------------|-------------------|-------------|
| long-lived process with memory | microVM freezes after each invocation, recycled unpredictably | in-memory counters **reset**; accumulation lost |
| Prometheus can reach us | Lambda exposes no stable, scrapeable port | **nobody can scrape `/metrics`** |
| one process | many concurrent executions | each has its own memory; nothing sums them |

That is why `.chalice/config.json` historically set `METRICS_ENABLED: "false"`
in `prod`: the scrape endpoint is meaningless there. **But metrics still must
work in prod** — via a different mechanism.

---

## 3. The Lambda model: push one event per request (CloudWatch EMF)

Instead of *accumulate then expose*, each request **pushes** its dimensions to
CloudWatch using the **Embedded Metric Format (EMF)**. CloudWatch aggregates
(Count, average, p90, Sum) server-side across all concurrent invocations.

The `observe_request` logic (labels, 5xx handling) is **identical in spirit**;
only the storage backend differs. This is implemented in
`chalicelib/observability/metrics_lambda.py`.

### 3.1 The backend, wired additively
`pipeline.py` keeps calling `REGISTRY.observe_request(...)` **unconditionally**
(so the local model and every existing test are untouched) and *additionally*
pushes to CloudWatch **only when** the backend is `cloudwatch`:

```python
REGISTRY.observe_request(route, method, status, duration)
if get_config().metrics_backend == "cloudwatch":
    metrics_lambda.observe_request(route, method, status, duration)
    metrics_lambda.flush()
```

`metrics_lambda.observe_request` maps the same labels to EMF metrics
(`http_requests`, `request_duration_ms`, `http_errors`).

### 3.2 Why it never breaks locally
`metrics_lambda` imports `aws_lambda_powertools` **lazily**, inside a factory
that only runs when the sink isn't injected. On a dev machine the backend is
`inproc`, that code never executes, and Powertools is not required. Tests
inject a fake sink (see `tests/unit/test_metrics_lambda.py`) so no AWS SDK is
needed to reach 100% coverage.

---

## 4. Configuration: how the backend is chosen

`chalicelib/config.py` gained two settings (defaults preserve today's behavior):

| Env var | Values | Meaning |
|---------|--------|---------|
| `METRICS_BACKEND` | `inproc` \| `cloudwatch` | where `observe_request` sends data |
| `AWS_LAMBDA_FUNCTION_NAME` | set / unset | presence ⇒ `on_lambda = True` |

Auto-selection: if running on Lambda and `METRICS_BACKEND` is unset, it
defaults to `cloudwatch`; otherwise `inproc`. Invalid values raise at startup.

Readiness (`/ready`) now treats `cloudwatch` as metrics "on", so a prod Lambda
that has the scrape endpoint disabled is still **ready** (verified in
`tests/unit/test_services.py::test_readiness_cloudwatch_backend_makes_prod_ready`).

---

## 5. Deploying to Lambda

### 5.1 Prereqs
```bash
pip install chalice              # packaging/deploy CLI
aws configure                    # or export AWS_PROFILE
```
`requirements-lambda.txt` adds `aws-lambda-powertools` on top of the normal
`requirements.txt`. Install it for the deploy target (Chalice bundles
`requirements.txt`; add the lambda file for prod):
```bash
make deploy          # == scripts/deploy_lambda.sh  (validate→package→deploy)
```
The deploy script runs the quality gate first (if the stack is up), then
`chalice package` + `chalice deploy`.

### 5.2 IAM
`.chalice/policy-prod.json` grants the Lambda the single extra permission EMF
needs (scoped to our namespace):
```json
{ "Effect": "Allow", "Action": ["cloudwatch:PutMetricData"],
  "Resource": "*",
  "Condition": { "StringEquals": { "cloudwatch:namespace": "ChaliceLab" } } }
```

### 5.3 Stage env (`.chalice/config.json`)
The `prod` stage sets `METRICS_BACKEND: "cloudwatch"` and keeps
`METRICS_ENABLED: "false"` (no scrape route on Lambda). The metrics are real;
they just land in CloudWatch instead of `/metrics`.

---

## 6. Seeing the metrics (3 options)

1. **CloudWatch native (zero extra infra)**
   ```bash
   aws cloudwatch list-metrics --namespace ChaliceLab
   aws cloudwatch get-metric-statistics --namespace ChaliceLab \
     --metric-name http_requests --statistics Sum --period 60 \
     --start-time ... --end-time ... --dimensions Name=route,Value=/hello
   ```
   Build a CloudWatch dashboard + alarms on `http_errors` / p90 latency.
2. **Grafana with the CloudWatch data source** — point a Grafana CloudWatch
   data source at `ChaliceLab`; your dashboards read Lambda metrics directly.
3. **Keep your Prometheus stack (the push↔pull bridge)** — run
   `prometheus-cloudwatch-exporter` on a durable host (Fargate/EC2): it *pulls*
   CloudWatch and exposes `/metrics`, which your existing Prometheus scrapes and
   Grafana plots. This preserves your current dashboards with almost no change.

> Also free with no code: API Gateway `Count`/`Latency` and Lambda
> `Invocations`/`Errors`/`Duration`/`Throttles` are emitted automatically. Use
> them for coarse SRE; the EMF metrics above carry your `route`/`method` labels.

### 6.1 About SonarQube on Lambda
SonarQube is a **code-quality** tool that runs in CI (the ephemeral scan you saw
in GitHub Actions). It is not a runtime dependency of the deployed Lambda, so
nothing about metrics affects it. CI keeps scanning; Lambda keeps pushing to
CloudWatch. Two separate concerns.

---

## 7. Alternative: OpenTelemetry (vendor-neutral)

If you want traces + metrics and portability off AWS, use **AWS Distro for
OpenTelemetry (ADOT)**: a Lambda layer auto-instruments Chalice/HTTP and exports
spans/metrics to X-Ray/CloudWatch, or to an OTel collector that does
Prometheus **remote-write**. More moving parts, but a superset of the EMF
approach. The current EMF backend is the smallest change that makes metrics work
on Lambda; ADOT is the "graduate" path.

---

## 8. What changed in the codebase (summary)

| File | Change |
|------|--------|
| `chalicelib/config.py` | `metrics_backend`, `on_lambda`; auto-default on Lambda; validation |
| `chalicelib/observability/metrics_lambda.py` | **new** — CloudWatch EMF backend (lazy Powertools) |
| `chalicelib/observability/pipeline.py` | additive CloudWatch push/flush when backend=cloudwatch; `REGISTRY` call unchanged |
| `chalicelib/services/readiness.py` | `cloudwatch` counts as metrics "on" |
| `.chalice/config.json` | prod sets `METRICS_BACKEND=cloudwatch` |
| `.chalice/policy-prod.json` | adds scoped `cloudwatch:PutMetricData` |
| `requirements-lambda.txt` | adds `aws-lambda-powertools` (Lambda-only) |
| `scripts/deploy_lambda.sh`, `make deploy` | gate → package → deploy helper |
| `tests/unit/{test_config,test_metrics_lambda,test_pipeline,test_services}.py` | cover the new backend + selection |

**Local is unchanged**: `make start`, `make validate`, `/metrics`, Prometheus
and Grafana behave exactly as before. The Lambda path is opt-in via
`METRICS_BACKEND=cloudwatch`.
