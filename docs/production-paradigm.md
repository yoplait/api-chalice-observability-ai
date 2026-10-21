# Production Paradigm: ECS Containers vs Local Lab

This document explains how to move the "closed loop" of the local lab (Prometheus + Docker Compose + Exporters) to a real AWS production environment. The target setup matches your actual infrastructure: **Grafana on ECS, CloudWatch for logs/metrics, and everything else running as ECS containers**.

## 1. The Local Lab (How it works now)

Everything runs in a closed Docker loop. Prometheus "pulls" data from containers that expose `/metrics`. Blackbox and statuspage exporters run as simple containers on the same network. Grafana reads from Prometheus.

```text
[Local Docker Network]
chalice-api --> /metrics
blackbox-exporter --> pings /health (Probe)
statuspage-exporter --> pings Okta/Twilio (Export)
[Prometheus] --> scrapes all /metrics (Pull)
[Grafana] --> reads Prometheus (Visualization)
```

## 2. The Production Environment (ECS Containers + CloudWatch)

In production, there is no Prometheus scraping containers. Instead, everything runs as **ECS containers** (or uses native AWS services), and Grafana sits on ECS reading from CloudWatch.

### How each piece translates to ECS:

| Local Lab Component | Production Equivalent (ECS) | How it works |
|---------------------|-----------------------------|--------------|
| **Prometheus** | **ECS Service** (if you want parity) OR **CloudWatch Metrics** (native) | If you keep the same architecture, run Prometheus as an ECS task that scrapes your apps. If you prefer cloud-native, skip Prometheus entirely and use CloudWatch Metrics. |
| **App `/metrics` route** | **Push to CloudWatch** (Code already exists) | The app writes metrics directly to CloudWatch using `metrics_lambda.py`. No scrape needed. |
| **Grafana** | **ECS Task** (unchanged) | Connects to CloudWatch Logs/Metrics instead of Prometheus. Same dashboards, different data source. |
| **Blackbox Exporter** | **ECS Task** | Runs the same `prom/blackbox-exporter` container on ECS. Pings your API from inside the VPC or via a public ALB. |
| **Statuspage Exporter** | **ECS Task** | Runs your exporter script as an ECS container. Schedules checks every few minutes and writes results to CloudWatch. |
| **Logs** | **CloudWatch Logs** | Your app already writes JSON logs. ECS forwards them to CloudWatch. Grafana parses them directly. |

## 3. The Plain-English Flow

1. **Your API** runs on ECS. Every request is logged as JSON and sends metrics to CloudWatch.
2. **Blackbox container** runs on ECS. It makes HTTP calls to your API endpoints (`/health`, `/hello`, etc.) and logs success/failure to CloudWatch.
3. **Exporter containers** (statuspage, etc.) run on ECS. They run on a schedule, check external services, and write the results to CloudWatch.
4. **CloudWatch** collects all the logs and metrics. It acts as your central time-series and log storage.
5. **Grafana on ECS** connects to CloudWatch. It reads the metrics and logs, and shows the exact same graphs you have in the lab.

**No Prometheus needed unless you specifically want it.** If you keep it, it runs as an ECS container just like everything else. If you drop it, CloudWatch handles the same job natively.

## 4. What changes in the code

| File | Change for Production |
|------|-----------------------|
| `chalicelib/observability/metrics.py` | Keeps the in-process counter (local only). |
| `chalicelib/observability/metrics_lambda.py` | Already written. Pushes to CloudWatch when `METRICS_BACKEND=cloudwatch`. |
| `chalicelib/observability/pipeline.py` | Calls both local registry AND cloudwatch push when on ECS/Lambda. |
| `.chalice/config.json` | `prod` stage sets `METRICS_BACKEND=cloudwatch`. |
| `Dockerfile` (Grafana) | Already prepared. Runs on ECS with CloudWatch datasource. |

**No other code changes required.** The exporters and probes are just Docker containers. You run them on ECS exactly like you run Grafana.

## 5. Roadmap to production

1. **Deploy the app** to ECS (via Chalice/Lambda or ECS Fargate). Enable `METRICS_BACKEND=cloudwatch`.
2. **Deploy Prometheus on ECS** (optional). If you want the exact lab behavior, run it as an ECS service and scrape your apps.
3. **Deploy exporters as ECS tasks**: blackbox-exporter, statuspage-exporter, etc. Point them at your app's internal or public endpoint.
4. **Deploy Grafana on ECS** (already have the Dockerfile). Add CloudWatch as a data source. Import your existing dashboards.
5. **Connect CloudWatch Logs**: Your app already writes JSON. Grafana can query CloudWatch Logs directly.

This keeps your architecture consistent: **everything is a container in ECS**, except where AWS native services (CloudWatch) are simpler. No X-Ray, no forced Lambda jumps, just the same container mindset you already use locally.