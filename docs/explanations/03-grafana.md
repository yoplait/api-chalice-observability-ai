# Grafana — the visualization layer

## What it is

Grafana is a web app that turns numbers into charts and colors. It does **not**
store data and does **not** collect it. It asks a data source (here, Prometheus)
a question and draws the answer.

Think of it as the dashboard of a car: the sensors (exporters) measure, the
wiring + ECU (Prometheus) records, and the dials (Grafana) show you "speed 90,
engine temp red".

## How it connects to Prometheus

Grafana is configured with a **data source** that points at Prometheus inside
the Docker network:

```yaml
# monitoring/grafana/provisioning/datasources/
- name: Prometheus
  uid: chalice-prom
  type: prometheus
  url: http://prometheus:9090   # Docker service name, not localhost
```

Every panel in a dashboard contains a PromQL query (e.g.
`avg_over_time(probe_success[5m])`). When you open the dashboard, Grafana sends
that query to Prometheus and paints the result.

## Provisioning: dashboards as code

Dashboards are **files**, not hand-made screens. They live in
`monitoring/grafana/dashboards/*.json` and are loaded automatically on startup
by a provider (`monitoring/grafana/provisioning/dashboards/provider.yml`).
That means they are version-controlled and reproducible — no clicking around.

## The two dashboards in this lab

1. **AWS Chalice API — Observability** — 12 panels built on the
   blackbox-exporter metrics (is our API up, how fast, error rate, latency).
2. **External API & Status Pages Monitoring** — built on the
   statuspage-exporter metrics (are Okta/Twilio/GitHub/Stripe/Google having an
   incident). Turns red on a real third-party incident.

## Useful URLs

- Grafana UI: http://localhost:3001 (login `admin`, password via `make credentials`)
- Health check: http://localhost:3001/api/health

## One-line summary

Grafana = the screen. It queries Prometheus and draws charts; it stores nothing
and collects nothing itself.
