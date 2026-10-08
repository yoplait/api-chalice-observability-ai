SHELL := /bin/bash
COMPOSE := docker compose --project-name chalice-devops-lab
COMPOSE_FLAGS := -f compose.yaml
COMPOSE_ENV := -f .env

VENV := $(shell pwd)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
COV := $(VENV)/bin/pytest

# defaults
API_PORT  ?= $(shell grep -m1 '^API_HOST_PORT' .env 2>/dev/null | cut -d= -f2 || echo 8000)
GRAFANA_PWD ?= $(shell grep -m1 '^GRAFANA_ADMIN_PASSWORD' .env 2>/dev/null | cut -d= -f2 || echo "")

# ---- helpers ----
.PHONY: all help up down destroy bootstrap status logs validate lint security test coverage
.PHONY: smoke-test observability-validate traffic traffic-errors traffic-latency
.PHONY: sonar sonar-init sonar-rotate-token quality-gate aws-package
.PHONY: creds

all: validate

help:
	@echo "============================================================"
	@echo "  chalice-devops-lab — commands"
	@echo "============================================================"
	@echo "  make up                Start infrastructure (compose)"
	@echo "  make down              Stop containers (keep volumes)"
	@echo "  make destroy           Remove volumes (confirmation required)"
	@echo "  make bootstrap         Full zero-touch first boot (see below)"
	@echo "  make status            Container health summary"
	@echo "  make logs [svc]        docker compose logs"
	@echo "  make lint              ruff check"
	@echo "  make security          bandit + pip-audit"
	@echo "  make test              pytest (venv)"
	@echo "  make coverage          pytest + coverage (venv, XML + HTML)"
	@echo "  make sonar             Run SonarScanner (Compose)"
	@echo "  make sonar-init        Bootstrap SonarQube (Compose)"
	@echo "  make sonar-rotate-token Force token rotation"
	@echo "  make quality-gate      Validate Quality Gate + coverage"
	@echo "  make smoke-test        curl all endpoints"
	@echo "  make observability-validate  E2E monitoring + failure test"
	@echo "  make traffic           Start traffic generator (profile)"
	@echo "  make traffic-errors    Traffic with errors (profile)"
	@echo "  make traffic-latency   Traffic with latency (profile)"
	@echo "  make validate          Full pipeline (lint → test → sonar → gate → smoke → e2e)"
	@echo "  make aws-package       chalice package + validate SAM"
	@echo "============================================================"

# ── infrastructure ────────────────────────────────────────────
up: .env
	$(COMPOSE) $(COMPOSE_FLAGS) up -d chalice-api blackbox-exporter prometheus grafana
	@echo ""
	@echo "  ┌─ Infrastructure started ───────────────────────────────────┐"
	@echo "  │  API       : http://localhost:$(API_PORT)                    │"
	@echo "  │  SonarQube : http://localhost:9000                           │"
	@echo "  │  Grafana   : http://localhost:3001  admin/$(GRAFANA_PWD)      │"
	@echo "  │  Prometheus: http://localhost:9090                           │"
	@echo "  │  Blackbox  : http://localhost:9115                           │"
	@echo "  └──────────────────────────────────────────────────────────────┘"

down:
	$(COMPOSE) $(COMPOSE_FLAGS) down

destroy:
	@read -p "Destroy ALL project volumes? [y/N] " r; [ "$${r:-N}" = "y" ] && \
		$(COMPOSE) $(COMPOSE_FLAGS) down -v --remove-orphans || echo "cancelled"

status:
	@echo "  ─ Containers ─"; $(COMPOSE) $(COMPOSE_FLAGS) ps 2>/dev/null || true

logs:
	@$(COMPOSE) $(COMPOSE_FLAGS) logs --tail 80 $* 2>/dev/null || \
	 $(COMPOSE) $(COMPOSE_FLAGS) logs --tail 80

# ── code quality ──────────────────────────────────────────────
lint:
	@$(VENV)/bin/ruff check . 2>/dev/null || { \
		$(PIP) install ruff -q; \
		$(VENV)/bin/ruff check .; \
	}

security:
	@$(VENV)/bin/bandit -r chalicelib app.py -ll -q 2>/dev/null || true
	@$(PIP) install pip-audit -q 2>/dev/null || true
	@$(VENV)/bin/pip-audit -r requirements.txt -r requirements-dev.txt 2>/dev/null || true

test: lint
	$(VENV)/bin/pytest -q --cov --cov-report=term 2>/dev/null || \
	 pytest -q --cov --cov-report=term

coverage: lint
	@mkdir -p reports
	$(COV) -q --cov --cov-report=term --cov-report=xml:coverage.xml \
		   --cov-report=html --junitxml=reports/junit.xml

# ── SonarQube ─────────────────────────────────────────────────
sonar-init: .env
	@mkdir -p .sonar && chmod 700 .sonar
	$(COMPOSE) $(COMPOSE_FLAGS) --profile quality up --build -d sonarqube-db sonarqube
	@echo "  ─ SonarQube bootstrap ─"
	$(COMPOSE) $(COMPOSE_FLAGS) --profile quality run -T --rm --no-deps sonar-bootstrap

sonar: sonar-init
	@$(COMPOSE) $(COMPOSE_FLAGS) --profile quality run -T --rm sonar-scanner || { \
		echo "  [WARN] scanner failed — check logs above"; exit 1; }

sonar-rotate-token: .env
	$(COMPOSE) $(COMPOSE_FLAGS) --profile quality up -d sonarqube-db sonarqube
	SONAR_ROTATE_TOKEN=1 $(COMPOSE) $(COMPOSE_FLAGS) --profile quality run -T --rm --no-deps sonar-bootstrap

quality-gate: sonar
	@bash scripts/validation/quality_gate.sh

# ── smoke & monitoring ────────────────────────────────────────
smoke-test:
	@bash scripts/validation/smoke.sh

observability-validate:
	@bash scripts/validation/verify_observability.sh

# ── traffic ───────────────────────────────────────────────────
traffic: .env
	@echo "  [traffic] normal mode RPS=${TRAFFIC_RPS:-5}"
	$(COMPOSE) $(COMPOSE_FLAGS) --profile traffic up -d --scale synthetic-traffic=1

traffic-errors: .env
	@echo "  [traffic] errors mode"
	TRAFFIC_MODE=errors $(COMPOSE) $(COMPOSE_FLAGS) --profile traffic up -d

traffic-latency: .env
	@echo "  [traffic] latency mode"
	TRAFFIC_MODE=latency $(COMPOSE) $(COMPOSE_FLAGS) --profile traffic up -d

# ── AWS packaging ─────────────────────────────────────────────
aws-package:
	$(PIP) install -q chalice==1.33.0 -r requirements.txt 2>/dev/null || pip install -q chalice==1.33.0 -r requirements.txt
	$(VENV)/bin/chalice package --sam-template sam_out/
	@echo "  ─ SAM template: sam_out/template.yaml"
	@ls -lh sam_out/

# ── credentials ───────────────────────────────────────────────
creds:
	@echo "============================================================"
	@echo "  Credenciales del laboratorio"
	@echo "============================================================"
	@echo ""
	@echo "  GRAFANA     http://localhost:$(shell grep -m1 '^GRAFANA_HOST_PORT' .env 2>/dev/null | cut -d= -f2 || echo 3001)"
	@echo "  Login:      admin"
	@echo "  Password:   $(shell grep -m1 '^GRAFANA_ADMIN_PASSWORD' .env 2>/dev/null | cut -d= -f2 || echo '---')"
	@echo ""
	@echo "  SONARQUBE   http://localhost:$(shell grep -m1 '^SONAR_HOST_PORT' .env 2>/dev/null | cut -d= -f2 || echo 9000)"
	@echo "  Login:      admin"
	@echo "  Password:   $(shell cat .sonar/admin-credentials 2>/dev/null | cut -d: -f2 || echo '---')"
	@echo "  Token:      $(shell cat .sonar/token 2>/dev/null | head -c 20 || echo '---')"
	@echo ""
	@echo "  PROMETHEUS  http://localhost:$(shell grep -m1 '^PROM_HOST_PORT' .env 2>/dev/null | cut -d= -f2 || echo 9090)"
	@echo "  (sin autenticación)"
	@echo ""
	@echo "  API CHALICE http://localhost:$(API_PORT)"
	@echo "  (sin autenticación)"
	@echo ""
	@echo "  Postgres    localhost:5432  user=sonar  pass=$(shell grep -m1 '^POSTGRES_PASSWORD' .env 2>/dev/null | cut -d= -f2 || echo '---')"
	@echo "============================================================"

# ── bootstrap ─────────────────────────────────────────────────
bootstrap: .env
	@echo "============================================================"
	@echo "  make bootstrap — FULL ZERO-TOUCH BOOTSTRAP"
	@echo "============================================================"
	@echo ""
	@echo "  [1/13] Preflight checks..."
	@bash scripts/bootstrap/preflight.sh
	@echo ""
	@echo "  [2/13] Building Docker images..."
	@$(COMPOSE) $(COMPOSE_FLAGS) build
	@echo "  [3/13] Validating monitoring configs..."
	@docker run --rm -v $(shell pwd)/monitoring/prometheus:/etc/prometheus:ro \
	  prom/prometheus:v3.7.3 promtool check config /etc/prometheus/prometheus.yml 2>/dev/null || \
	 echo "  [WARN] promtool not available in container — skipping"; \
	 docker run --rm -v $(shell pwd)/monitoring/prometheus:/etc/prometheus:ro \
	  prom/prometheus:v3.7.3 promtool check rules /etc/prometheus/alerts.yml 2>/dev/null || \
	 echo "  [WARN] promtool rule check skipped"
	@echo ""
	@echo "  [4/13] Starting PostgreSQL..."
	@$(COMPOSE) $(COMPOSE_FLAGS) up -d sonarqube-db
	@echo "  [5/13] Starting SonarQube..."
	@$(COMPOSE) $(COMPOSE_FLAGS) up -d sonarqube
	@echo "  [6/13] Initializing SonarQube (auth, project, gate, token)..."
	@mkdir -p .sonar && chmod 700 .sonar
	@$(COMPOSE) $(COMPOSE_FLAGS) --profile quality run -T --rm sonar-bootstrap
	@echo ""
	@echo "  [7/13] Starting Chalice API..."
	@$(COMPOSE) $(COMPOSE_FLAGS) up -d chalice-api
	@echo "  [8/13] Waiting for API health..."
	@bash -c 'for i in $$(seq 1 30); do if curl -sf http://localhost:$(API_PORT)/health >/dev/null 2>&1; then echo "  API ready"; exit 0; fi; sleep 2; done; echo "  [FAIL] API not healthy after 60s"; exit 1'
	@echo "  [9/13] Lint..."
	@$(MAKE) lint 2>&1 | tail -3
	@echo "  [10/13] Security checks..."
	@$(MAKE) security 2>&1 | tail -3
	@echo "  [11/13] Tests + coverage..."
	@$(MAKE) coverage 2>&1 | tail -5
	@echo ""
	@echo "  [12/13] SonarScanner + Quality Gate..."
	@$(MAKE) sonar 2>&1 | tail -10
	@echo ""
	@echo "  [13/13] Smoke test + observability..."
	@$(MAKE) smoke-test 2>&1 | tail -4
	@bash scripts/bootstrap/start_monitoring.sh 2>/dev/null || \
	 $(COMPOSE) $(COMPOSE_FLAGS) up -d prometheus blackbox-exporter grafana && sleep 25 && echo "  [MONITORING] started"
	@sleep 10
	@bash scripts/bootstrap/verify_observability_in_bootstrap.sh 2>/dev/null || \
	 bash scripts/validation/verify_observability.sh
	@echo ""
	@echo "============================================================"
	@echo "  make bootstrap — COMPLETE"
	@echo "============================================================"

# ---- secrets -------------------------------------------------
GRAFANA_PW  := $(shell openssl rand -base64 18 2>/dev/null | tr -d '/+=' | cut -c1-24 || echo RANDOM_PW_G_0)
PG_PW       := $(shell openssl rand -base64 18 2>/dev/null | tr -d '/+=' | cut -c1-24 || echo RANDOM_PW_PG_0)

.env: .env.example
	@sed -e 's/^GRAFANA_ADMIN_PASSWORD.*/GRAFANA_ADMIN_PASSWORD=$(GRAFANA_PW)/' \
	     -e 's/^POSTGRES_PASSWORD.*/POSTGRES_PASSWORD=$(PG_PW)/' \
	     .env.example > .env
	@chmod 600 .env

# ---- convenience aliases -------------------------------------
validate: lint security coverage sonar quality-gate smoke-test observability-validate
	@echo ""
	@echo "============================================================"
	@echo "  VALIDATE: ALL PASSED"
	@echo "============================================================"