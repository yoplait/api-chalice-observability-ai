# Prometheus — the time-series database

## What it is

Prometheus is a database that stores **numbers over time** (a "time series").
Every value it keeps has a timestamp and a set of labels:

```
http_requests_total{route="/hello", method="GET", status="2xx"}  1027
```

It is not a general database (no users table, no joins). It is built for one
job: remember "what was the value of this metric at this moment", and answer
questions like "average latency over the last 5 minutes".

## How it collects data: scraping

Prometheus does **not** receive data pushed to it. It **pulls**. Every 15
seconds it walks down a list of targets and fetches each one's `/metrics` page.

The list of targets is written by hand in `monitoring/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: chalice-app
    metrics_path: /metrics
    static_configs:
      - targets: ["chalice-api:8000"]
  - job_name: statuspage-exporter
    static_configs:
      - targets: ["statuspage-exporter:9118"]
```

There is no auto-discovery here: if you add an exporter tomorrow, you must add
its `targets:` line yourself.

### Why the targets are Docker names, not localhost

Inside Docker Compose every service is reachable by its **service name** as a
hostname (Docker's internal DNS). Prometheus runs in the same network, so it
talks to `chalice-api:8000`, not `localhost:8080`.

| From where | You write |
|------------|-----------|
| Your browser / host | `http://localhost:8080` |
| Prometheus (inside Docker) | `http://chalice-api:8000` |

The `ports:` mapping in `compose.yaml` exists only so the host can reach a
container; Prometheus does not need it.

## What it does with the data

- **Stores** it in its own on-disk format (a TSDB) with a retention window
  (this lab: 15 days).
- **Evaluates alert rules** (`monitoring/prometheus/alerts.yml`) — e.g. "if
  `probe_success` is 0 for 2 minutes, fire an alert".
- **Answers queries** through its HTTP API and the PromQL language, which is
  what Grafana calls.

## Useful URLs in this lab

- Web UI + queries: http://localhost:9090
- Active scrape targets and their health: http://localhost:9090/targets
- Current alerts: http://localhost:9090/alerts
- Query API: `curl 'http://localhost:9090/api/v1/query?query=up'`

## One-line summary

Prometheus = a database of numbers-over-time that **pulls** metrics from a
hand-written list of targets and answers questions about them.
