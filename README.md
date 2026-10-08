# AWS Chalice DevSecOps & Observability Lab

A fully reproducible, zero-touch local DevOps platform for an AWS Chalice REST API. One command initializes everything: `make bootstrap`.

**What it includes:** Chalice API (hello/health/ready/version/demo endpoints) · pytest with 100% coverage · SonarQube (cold-start auth, project, Quality Gate, token management) · Prometheus + Blackbox Exporter · Grafana with 12-panel dashboard · synthetic traffic generator · full observability validation with failure simulation & recovery.

---

## Prerequisites

- macOS Apple Silicon (ARM64) — verified on macOS 14.8.5.
- Docker Desktop ≥ 4.30 (Docker Engine 29.x) with Docker Compose v2+.
- Python 3.12 (virtualenv).
- ~8 GiB RAM on the Docker Desktop VM (SonarQube + PostgreSQL are the heaviest services).

**Known limitation:** The official `sonarsource/sonar-scanner-cli` image publishes **amd64 only**. On this ARM64 host, running the image under emulation crashes the launcher. The project builds a local ARM64 scanner image (`docker/sonar-scanner/Dockerfile`) that extracts the portable scanner distribution from the upstream image and runs it on an `eclipse-temurin:21-jre` base. No emulation is needed.

---

## Quick Start

```bash
# 1. Start Docker Desktop (if not running)

# 2. One command — everything:
make bootstrap
```

This single command: builds images, starts PostgreSQL + SonarQube, boots SonarQube
automatically (admin init, project, Quality Gate, scanner token), starts the Chalice API, runs lint/security/tests/coverage, runs SonarScanner, validates the Quality Gate, starts Prometheus/Blackbox/Grafana, validates monitoring, generates synthetic traffic, and runs an end-to-end observability validation with failure simulation and recovery.

**Expected total time: ~8–15 minutes** (first SonarQube boot can take 2–4 minutes on 4 CPU / 8 GiB).

---

## URLs & Ports

| Service | URL | Port | Credentials |
|---------|-----|------|-------------|
| Chalice API | http://localhost:8000 | 8000 | — |
| SonarQube | http://localhost:9000 | 9000 | admin / (generated, in `.sonar/admin-credentials`) |
| Grafana | http://localhost:3000 | 3000 | admin / (generated, in `.env`) |
| Prometheus | http://localhost:9090 | 9090 | — |
| Blackbox Exporter | http://localhost:9115 | 9115 | — |
| Prometheus Alerts | http://localhost:9090/alerts | 9090 | — |

PostgreSQL (5432) and internal Docker networks are **not** exposed to the host.

---

## API Endpoints (curl examples)

```bash
# Hello World
curl http://localhost:8000/hello
curl http://localhost:8000/hello?name=DevOps

# Health & Readiness
curl http://localhost:8000/health
curl http://localhost:8000/ready

# Version
curl http://localhost:8000/version

# Internal metrics (Prometheus format — local only)
curl http://localhost:8000/metrics

# Demo: controlled errors (disabled in prod)
curl http://localhost:8000/demo/error?kind=bad_request
curl http://localhost:8000/demo/error?kind=unavailable
curl http://localhost:8000/demo/error?kind=boom

# Demo: controlled latency
curl http://localhost:8000/demo/slow?delay=0.5

# Demo: unhandled exception path
curl http://localhost:8000/demo/exception
```

---

## Makefile Commands

| Command | What it does |
|---------|-------------|
| `make up` | Start infrastructure (API + monitoring) |
| `make down` | Stop containers (keep volumes) |
| `make destroy` | Remove all project volumes (confirmation required) |
| `make bootstrap` | Full zero-touch first boot (recommended) |
| `make lint` | Ruff lint check |
| `make security` | Bandit + pip-audit |
| `make test` | Pytest |
| `make coverage` | Pytest + coverage (XML + HTML + JUnit) |
| `make sonar-init` | Bootstrap SonarQube (auth, project, gate, token) |
| `make sonar` | Run SonarScanner |
| `make quality-gate` | Validate SonarQube Quality Gate + coverage |
| `make smoke-test` | Curl all API endpoints |
| `make traffic` | Start traffic generator (normal mode) |
| `make traffic-errors` | Traffic generator with error scenarios |
| `make traffic-latency` | Traffic generator with latency scenarios |
| `make observability-validate` | Full E2E monitoring + failure/recovery test |
| `make validate` | Full pipeline: lint → security → test → sonar → gate → smoke → observability |
| `make aws-package` | `chalice package` + SAM template validation |

---

## SonarQube

- **First boot:** completely automated. `sonar-bootstrap` detects default `admin:admin`, generates a strong password, persists it to `.sonar/admin-credentials` (chmod 600, gitignored).
- **Scanner token:** a project-scoped token is generated and persisted to `.sonar/token` (chmod 600, gitignored). Used by the scanner service via environment variable — never printed in logs.
- **Token rotation:** `make sonar-rotate-token`.
- **Quality Gate:** custom gate with `line_coverage ≥ 100`, `branch_coverage ≥ 100`, `duplicated_lines_density ≤ 3`, `reliability_rating ≤ 1`, `security_rating ≤ 1` (Sonar Community may not enforce all via the API — the `quality_gate.sh` script enforces the branch/statement coverage locally from `coverage.xml`).

---

## Grafana Dashboards

**Dashboard: AWS Chalice API — Observability** (12 panels):
1. API Availability (stat)
2. Health Status (stat)
3. Readiness Status (stat)
4. Endpoint Comparison (bargauge)
5. Synthetic HTTP Response Time (timeseries)
6. Probe Success Rate (timeseries)
7. HTTP Probe Status Codes (timeseries)
8. Probe Duration breakdown (timeseries)
9. Prometheus Target Health (timeseries)
10. Application Request Rate (internal /metrics, timeseries)
11. Application Error Rate (internal /metrics, timeseries)
12. Application Latency p50/p95 (internal /metrics, timeseries)

Dashboards are version-controlled in `monitoring/grafana/dashboards/` and auto-provisioned on every `make up`.

---

## Synthetic Traffic & Failure Simulation

```bash
# Normal traffic
make traffic
# Traffic with errors
make traffic-errors
# Traffic with latency
make traffic-latency
```

To see monitoring in action:
1. Run `make traffic-errors` in one terminal.
2. Check Prometheus → Alerting tab — you should see alerts firing.
3. Check Grafana — the dashboard panels will reflect the traffic patterns.

---

## End-to-End Observability Validation

`make observability-validate` runs a scripted validation that:
1. Proves all services are healthy
2. Verifies Prometheus collects real data from all targets
3. Verifies Grafana dashboards show real data
4. Generates traffic and confirms new samples appear
5. **Stops the API** and verifies Blackbox detects the failure
6. **Restores the API** and verifies monitoring reports recovery

---

## Troubleshooting

### Docker Desktop not running
```bash
open -a Docker        # start Docker Desktop
sleep 10
docker ps             # verify
make up               # then proceed
```

### Port conflicts
Check with `lsof -iTCP:<port> -sTCP:LISTEN` and kill the process if needed. Default ports: 8000, 9000, 3000, 9090, 9115.

### SonarQube slow to start (first boot)
The first boot can take 2–4 minutes on 4 CPU / 8 GiB as it initializes ES shards and databases. The bootstrap polls `/api/system/status` until `UP` with a configurable timeout (default 300s). Do not `make down` during this time.

### SonarQube `admin:admin` won't change
If the admin password was already changed (e.g. from a previous run), the bootstrap reuses the stored credentials from `.sonar/admin-credentials`. To reset, delete `.sonar/admin-credentials` and re-run `make sonar-init`.

### Scanner token missing or invalid
```bash
make sonar-rotate-token
```

### Grafana dashboards not loading
Check that Grafana health returns `{"commit":"..."}`. If the datasource is disconnected, verify Prometheus is UP in the Prometheus UI.

---

## Local vs AWS

This lab validates the API under `chalice local`. Chalice packages the same code for Lambda/API Gateway, so the API logic is identical. Differences:

| Aspect | Local (`chalice local`) | AWS Lambda + API Gateway |
|--------|------------------------|---------------------------|
| HTTP handler | Python process, persistent | Cold/warm Lambda invocations |
| `/metrics` endpoint | ✅ scrapable by Prometheus | ❌ not accessible; use CloudWatch / OTel |
| Logging | JSON stdout | CloudWatch Logs |
| Correlation ID | ✅ generated & propagated | ✅ generated by API Gateway |
| Error handling | ✅ middleware + decorator | ✅ same via `chalice local` testing |
| Metrics | ✅ in-process counters | CloudWatch EMF / OpenTelemetry |
| Deploy | `chalice deploy` | Requires AWS credentials |

To validate the AWS deployment path: `make aws-package` generates a SAM template from your code. Run it without credentials to verify the package builds and the SAM template is valid.

---

## Project Structure

```
observe/
├── app.py                    # Chalice entrypoint
├── chalicelib/
│   ├── config.py             # Environment config (validation)
│   ├── errors.py             # Domain error model
│   ├── logging.py            # Structured JSON logging
│   ├── version.py
│   ├── handlers/
│   │   ├── core.py           # Main routes
│   │   ├── demo.py           # Demo/error routes
│   │   ├── views.py          # Error decorator
│   │   └── context.py        # Route template cache
│   ├── services/
│   │   ├── greeter.py
│   │   ├── readiness.py
│   │   └── validation.py
│   └── observability/
│       ├── metrics.py        # In-process Prometheus registry
│       └── pipeline.py       # HTTP middleware
├── tests/                    # pytest suite (100% coverage)
│   ├── unit/
│   ├── integration/
│   └── contract/
├── docker/                   # Dockerfiles (multi-stage)
├── monitoring/               # Prometheus / Blackbox / Grafana
├── sonar/bootstrap/          # SonarQube zero-touch bootstrap
├── scripts/                  # Validation & traffic
├── .chalice/config.json      # Chalice deploy config (dev/prod)
├── compose.yaml              # Full stack (11 services)
├── Makefile                  # All orchestration
├── pyproject.toml            # pytest, coverage, ruff, black, bandit
├── sonar-project.properties  # SonarQube scan config
├── .env.example              # Template (auto-generated as .env)
├── .gitignore
└── README.md
```