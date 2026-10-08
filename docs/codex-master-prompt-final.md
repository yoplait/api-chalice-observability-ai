# MASTER PROMPT (v2 FINAL) — AWS Chalice DevSecOps & Observability Lab
# Corregido contra el entorno real verificado el 2026-10-08 (macOS 14.8.5, Apple Silicon, Docker 29.5.3).
# Cambios frente al borrador anterior: ruta real del workspace, Compose v2+, bloque "VERIFIED FRAMEWORK
# CONSTRAINTS" en §3, estrategia ARM64 del SonarScanner en §4, PostgreSQL 16 fijado, gating de
# autenticación en el cold start de SonarQube (§6/§7), campo VALIDATION SCOPE en el informe (§25).

## YOUR ROLE
Act as a Principal AWS Cloud Architect, Senior DevOps Engineer, SRE, Python Backend Engineer,
DevSecOps Specialist and Observability Engineer.
Your task is to DESIGN, IMPLEMENT, EXECUTE, TEST, TROUBLESHOOT AND VALIDATE a fully functional AWS
Chalice DevSecOps laboratory. Create a complete working project, not just explain one. Own the
entire lifecycle from empty directory to fully operational, tested and observable API.

**Main objective: ZERO-TOUCH AUTOMATION.** Once generated, the user executes a single `make
bootstrap` that initializes everything: infrastructure, SonarQube authentication and tokens,
quality checks, monitoring, dashboards, traffic simulation and end-to-end verification. No manual
configuration on a normal first boot.
Do not fabricate results or report success for operations you have not executed.

# 1. LOCAL ENVIRONMENT (VERIFIED DATA — use it, do not re-probe what is already confirmed)
Project directory (work exclusively here):
`/Users/perezpardojc/Documents/code/nan/observe`

Environment:
- macOS 14.8.5 Apple Silicon **ARM64**.
- Docker Engine 29.5.3 linux/arm64, Docker Compose **v2+** (this host reports Compose v5.3.1).
- Docker Desktop VM resources: **4 CPUs / 8 GiB RAM**. Budget service memory accordingly
  (SonarQube+PostgreSQL are the heavy weights; keep steady state ≤ ~4 GiB).
- Python 3.12.13 at `/opt/homebrew/bin/python3.12`; venv required.
- AWS Chalice == 1.33.0 (verified working on 3.12). Local execution must NOT need AWS credentials.
- No paid third-party services.
- ARM64-native image availability VERIFIED on this host: `sonarqube:community`,
  `postgres:16-alpine`, `alpine:3.20`, `prom/prometheus:v3.7.3`,
  `prom/blackbox-exporter:v0.27.0`, `grafana/grafana:12.1.1`, `python:3.12-slim`.
- **NOT ARM64 (verified)**: `sonarsource/sonar-scanner-cli` publishes amd64 only for every tag, and
  running the upstream image under amd64 emulation on this host CRASHES the native launcher
  (`Failed to find vdso DT_HASH`), even with `--entrypoint sh`.
  → Build a local ARM64 scanner image instead: multi-stage Dockerfile that pulls
  `FROM --platform=linux/amd64 sonarsource/sonar-scanner-cli:latest AS dist` (layers are only read,
  never executed, so the crash does not matter) and `COPY --from=dist /opt/sonar-scanner` into
  `eclipse-temurin:21-jre` (arm64). The distribution is portable: `bin/sonar-scanner` is a POSIX sh
  script and `lib/sonar-scanner-cli-8.1.0.6389.jar` is plain Java bytecode. Pin the upstream image
  by digest and document the limitation.
- `vm.max_map_count`: cannot be set on the macOS host; the Docker Desktop VM usually ships >=262144.
  Preflight must check `docker run --rm alpine:3.20 sysctl vm.max_map_count`; if <262144, use a
  privileged one-shot init container to set it inside the VM. Never touch host config without
  authorization.
- Use pinned dependency versions and container image tags/digests. Detect port conflicts and report
  them clearly (default plan: API 8000, SonarQube 9000, Grafana 3000, Prometheus 9090,
  Blackbox 9115; PostgreSQL NOT exposed to host).

# 2. DESIRED ARCHITECTURE
Keep this architecture, modular and maintainable:

```text
DEVELOPER → make bootstrap → DOCKER COMPOSE LAB
  ├── CHALICE API (/hello /health /ready /version /demo/*)
  ├── CODE QUALITY (Pytest → Coverage → SonarScanner → SonarQube → Quality Gate)
  ├── OBSERVABILITY (Blackbox Exporter → Prometheus → Grafana → Dashboards → Alerts)
  └── SYNTHETIC TRAFFIC → feeds all of the above
FUTURE AWS TARGET: API Gateway → Lambda → CloudWatch / OTel
```
Local implementation must stay compatible with the AWS Chalice programming model.
Do not replace Chalice with FastAPI or Flask.

# 3. AWS CHALICE REST API
Real AWS Chalice project with:
`GET /` (API info) · `GET /hello` · `GET /health` (liveness, lightweight, no external deps) ·
`GET /ready` (readiness, not mere process existence) · `GET /version` ·
`GET /demo/error` (controlled HTTP error) · `GET /demo/slow` (controlled latency) ·
`GET /demo/exception` (controlled unhandled exception path).

Requirements: JSON responses, correct status codes, modular architecture (routing vs services vs
config), environment variables, structured JSON logging, correlation IDs, error handling, input
validation, no hardcoded secrets, configurable timeouts, clear versioning. Demo endpoints disabled
in production. Native Chalice conventions. Runs locally via `chalice local` inside a container.

## VERIFIED FRAMEWORK CONSTRAINTS (Chalice 1.33 — do not rediscover these the hard way)
1. `@app.before_request`, `@app.after_request` and `@app.error_handler` are REMOVED. The only
   extension hook is `@app.middleware("http")` with signature `(request, get_response)`.
2. Exceptions raised in views are converted to generic 5xx/JSON *inside* the framework
   (`ChaliceViewError` and any other Exception) and never reach middleware. Only
   `chalice.app.ChaliceUnhandledError` propagates to middleware.
   → Centralized error mapping therefore lives in a view decorator (domain `ApiError` →
   envelope `{"error":{"code","title","detail","correlation_id"}}`), and unhandled paths are
   verified through the decorator's 500 branch. Document that `ChaliceViewError` subclasses must NOT
   be raised by app code.
3. View function parameters are NOT bound from query strings with type coercion: query params are
   read explicitly from `current_request.query_params` (always `str`) and validated/converted by
   your own code. Path parameters `{name}` are bound as `str`.
4. Blueprints are constructed as `Blueprint(__name__)` (single arg) and registered with
   `app.register_blueprint(bp)` (there is no `app.blueprint()`).
5. `chalice local --host 0.0.0.0 --port 8000` is the container entrypoint.

# 4. DOCKER COMPOSE
Complete `compose.yaml`: chalice-api, sonarqube, sonarqube-db (**postgres:16-alpine**, fixed),
sonar-bootstrap, sonar-scanner (local ARM64 image per §1), prometheus, blackbox-exporter, grafana,
synthetic-traffic, tests, and alertmanager only if actual notification routing is required.
ARM64-compatible images (per §1). Healthchecks. `depends_on` with `service_healthy` where it truly
gates the next step. Persistent named volumes. Internal Docker networks (containers communicate via
Compose DNS names, never `localhost`). Restricted host port exposure (DB internal-only). Restart
policies (one-shot jobs `restart: "no"`; long-running `unless-stopped`). `.env` from `.env.example`
(chmod 600, never committed). Compose profiles for optional/one-shot jobs. No permanent test or
scanner containers. Services must restart preserving state.

# 5. AUTOMATED COLD BOOT (acceptance requirement)
From empty Docker volumes, `make bootstrap` runs this sequence (idempotent, each step gated by a
real readiness check — healthchecks/polling/timeouts/retries, never fixed sleeps as the only
mechanism; a failed step stops dependents with nonzero exit and preserved diagnostics):

1 Preflight (docker, arch, RAM/disk, ports, sysctl, images). 2 Validate configs (promtool, compose
config, python version). 3 Build images. 4 Start PostgreSQL → wait `pg_isready`. 5 Start SonarQube →
poll `/api/system/status == UP` (§6). 6 Initialize SonarQube admin + verify AUTHENTICATED (§7).
7 Create/verify project. 8 Create/verify Quality Gate + conditions + associate project. 9 Generate/validate
scanner token. 10 Start Chalice API → wait `/health`. 11 Lint. 12 Security checks. 13 Unit+
integration tests. 14 Coverage reports (xml+html+junit). 15 SonarScanner run. 16 Wait server-side
compute (§8). 17 Quality Gate verified. 18 Start Blackbox + Prometheus → poll `/-/ready` →
`/api/v1/targets` UP → recent `probe_success`/`probe_duration_seconds` samples (§11/§12).
19 Start Grafana → wait health → verify datasource + connectivity + dashboard + panel queries
return data (§14). 20 Provision alerts (promtool-validated rules; alert behavior §16). 21 Synthetic
traffic → confirm new samples. 22 Controlled failure → confirm detection (respecting `for:`
durations). 23 Restore → confirm recovery. 24 Final PASS/FAIL report (§25).

Second run must not duplicate projects, tokens, gates, dashboards or alert rules.
Note for Codex: parts of this already exist in the repo (API `app.py`/`chalicelib`, pyproject,
venv). Keep/extend them; do not restart from scratch or rewrite working verified code.

# 6. SONARQUBE COLD START
Community Build with persistent PostgreSQL 16. Implement: PG readiness; `/api/system/status` polling
requiring `UP`; timeout configurable, default 300 s (first boot on this 8 GiB VM can take 2–4 min);
retry interval; startup diagnostics (dump `sonarqube`/`db` logs on failure); resource + Elasticsearch
prerequisite verification (`vm.max_map_count` per §1); recovery after interrupted startup. Never
equate "container running" or "port open" with operational. Use APIs verified against the installed
release.
**Gating rule:** `status == UP` alone is NOT sufficient for bootstrap to proceed — authentication
must also be proven working first (see §7 step order), because the admin credentials may still be in
the initial state while the API already answers.

# 7. SONARQUBE FULLY AUTOMATED AUTHENTICATION (CRITICAL)
One-shot `sonar-bootstrap` service, no manual login ever:
1. Wait readiness (§6, including auth gate below).
2. Resolve first-boot admin init headlessly: try default `admin:admin`; if accepted, change it via
   the user-management Web API to a generated strong password persisted to `.sonar/admin-credentials`
   (chmod 600, gitignored); if the stored generated password authenticates, reuse it; verify
   authentication works before continuing (probe an authenticated endpoint such as
   `/api/projects/search`).
3. Create/verify project. 4. Create/verify custom Quality Gate + conditions + associate project.
5. Configure analysis permissions (project token user needs `Execute Analysis`/`Scan` + project
   roles; use a permission-scoped analysis token, NEVER the admin password/token for routine scans).
6. Generate project-scoped SonarScanner token ONCE, persist to `.sonar/token` (chmod 600).
7. Reuse the stored token while valid; detect invalid/revoked/missing token and regenerate using the
   retained admin credentials; support `make sonar-rotate-token`.
8. Recover from partially completed bootstrap without duplicating anything.

Hard rules: tokens cannot be re-read from SonarQube after creation (store at creation only); never
print tokens anywhere (logs, ps args, shell history — pass via env to containers, read from file);
never commit credentials; never reset persistent SonarQube data as a token-recovery shortcut; if
admin recovery is impossible, FAIL with clear instructions. Document where credentials live and how
to rotate them.

# 8. SONARQUBE PROJECT AND QUALITY GATE
Project key `chalice-devops-lab`. Analyze the real Python app; import `coverage.xml`. Appropriate
source/test exclusions. Objectives: 100% statement + 100% branch coverage of first-party code
(enforced by coverage.py `fail_under=100` in the pipeline; if Sonar Community cannot express an
exact condition — e.g. branch coverage 100 — enforce it in `quality-gate.sh` and say so; do NOT
claim Sonar enforced what another tool enforced). Duplicated lines < 3%. No new high-severity
findings, no new confirmed vulnerabilities, no blocking issues. Custom Quality Gate where supported.
Wait for background analysis (`is_queue_empty` + task SUCCESS + `computed`). `make quality-gate`
fails if the gate fails; successful upload is not sufficient.

# 9. PYTEST AND COVERAGE
Unit, integration, API contract, health, readiness, error handling, demo endpoints, config, negative
and boundary tests, using pytest, pytest-cov, coverage.py and Chalice-compatible mechanisms
(`chalice.test.Client` / LocalGateway) plus HTTP tests against the running container where
appropriate. Objective: **100% statement and branch coverage of first-party code** (`app.py`,
`chalicelib/**`). Generate `coverage.xml`, `htmlcov/`, terminal report and `reports/junit.xml`.
Correct exclusions for third-party/generated code; do not exclude application modules to reach the
target; no meaningless tests. Pipeline fails if statement OR branch target is missed.

# 10. CODE QUALITY AND SECURITY
Ruff, Black, Bandit (justified exclusions documented, never blanket silence), pip-audit over pinned
requirements, dependency pinning, container hardening where practical (non-root where viable),
secret detection, `.gitignore`, `.env.example`. Targets `make lint security test coverage` with
meaningful exit codes. No hardcoded keys/passwords/tokens.

# 11. PROMETHEUS FULL AUTOMATED BOOTSTRAP
Persistent storage (`prometheus-data` volume). `prometheus.yml` + alert rules + scrape configs +
target labels, version-controlled. Scrape interval 15 s. Monitor: Blackbox probes, Prometheus
itself, Chalice availability via Blackbox, application metrics ONLY if correctly instrumented
(`/metrics` endpoint in-process, documented as local-only per §13). Before start: `promtool check
config` + `check rules` + expected target check. After start: poll `/-/ready`; query
`/api/v1/targets`; required targets UP; query `probe_success`/`probe_duration_seconds`; verify
recent samples; all four endpoints represented. Bounded retries accounting for 15 s scrape + rule
evaluation. Container health alone is not operational.

# 12. BLACKBOX EXPORTER AUTOMATED BOOTSTRAP
Real HTTP probes for `/health`, `/ready`, `/hello`, `/version`. Modules validating expected status,
expected JSON content (body matchers), connection success, duration, timeouts; DNS/TCP timings
where applicable; `preferred_ip_protocol: ip4`. Endpoint labels differentiate probes; correct
Prometheus relabeling. Verify `/probe` directly and `probe_success == 1` in Prometheus for every
healthy endpoint. Targets resolve from Docker network. Test an intentionally failing endpoint and
verify failure is visible in Prometheus. A healthy exporter container ≠ successful monitoring.

# 13. APPLICATION METRICS
Distinguish: (A) External synthetic metrics from Blackbox (availability, synthetic latency, probe
status/failures, network timings) — never presented as measuring all user traffic. (B) Internal
application metrics where practical: total requests, RPS, handler duration, response codes,
exceptions, per-endpoint latency distribution, collected and rendered for real.
AWS reality: Lambda is not a permanently running scrape target — a persistent `/metrics` endpoint
does not work there; in-process counters reset per execution environment. Document production
alternatives: CloudWatch, EMF, OpenTelemetry, AWS collectors/extensions, CloudWatch→Prometheus
export. Preserve the local vs AWS runtime distinction everywhere.

# 14. GRAFANA ZERO-TOUCH PROVISIONING
File-based provisioning (versioned): secure local admin credentials (from `.env`, persisted with the
`grafana-data` volume; document rotation), Prometheus datasource with stable UID, dashboard folder,
dashboard **AWS Chalice API — Observability**, alerting rules where applicable. Required panels: API
Availability; API Health Status; API Readiness Status; Synthetic HTTP Response Time; Probe Success
Rate; HTTP Probe Status Codes; Probe Duration; Endpoint Comparison; Prometheus Target Health;
Application Request Rate / Error Rate / Latency Distribution (only if truly instrumented, per §13).
Valid PromQL; no fake/hardcoded values. Post-start validation via Grafana API: health; datasource
exists; connectivity OK; dashboard exists; panel configs; real Prometheus queries executed; recent
data present. A provisioned dashboard without valid data FAILS acceptance. Repeated bootstrap must
not duplicate dashboards/datasources.

# 15. SYNTHETIC TRAFFIC GENERATION
Real HTTP requests against Chalice: normal, burst, controlled latency, controlled HTTP errors,
recovery verification. Expose `make traffic`, `make traffic-errors`, `make traffic-latency`. Runs
via Compose profile/one-shot (no uncontrolled background processes). Configurable rate and duration.
Used to validate real monitoring behavior. Demo functionality must never be reachable in
production stage (config forces `demo_enabled=False` when `APP_STAGE=prod`).

# 16. ALERTING
Practical alerts: API Down; Readiness Failure; High Synthetic Latency; HTTP Probe Failure;
Monitoring Target Missing (distinguish API failure from monitoring-system failure). Prometheus rules
validated with promtool. Alertmanager only if used — then provisioned, readiness-verified, local
routing, no external notification credentials, local test receiver for demonstrable delivery.
Grafana alerts configured via provisioning where used; no duplicated alert ownership without
justification. Test the full lifecycle: healthy → controlled failure → detection → pending → firing
(after `for:`) → recovery → resolved, accounting for scrape + evaluation intervals. Never claim a
notification was delivered without verified delivery.

# 17. END-TO-END OBSERVABILITY VALIDATION
`scripts/verify-observability.sh` (or Python equivalent): call `/health`+`/hello`; verify JSON;
execute Blackbox probes; confirm probe success; query Prometheus; verify recent samples; query
Grafana datasource; verify dashboard; generate real traffic; wait new scrape samples; verify updated
values; simulate API unavailability; confirm Blackbox stored it; verify alert behavior; restore;
confirm recovery; produce evidence report. MUST restore the application even when a validation step
fails (trap/cleanup). No destructive scenarios against production AWS. Expose
`make observability-validate`.

# 18. MAKEFILE
```
make help | bootstrap | up | down | destroy | status | logs
make lint | security | test | coverage
make sonar-up | sonar-wait | sonar-init | sonar | quality-gate
make observability-validate | smoke-test
make traffic | traffic-errors | make traffic-latency
make validate | aws-package
```
bootstrap = complete first-time init incl. zero-touch Sonar credentials/tokens + all observability +
E2E verification; works on empty volumes. up = start preserving state. down = stop WITHOUT deleting
volumes. destroy = remove only project-owned containers/volumes/images, requires explicit
confirmation, never touches unrelated Docker resources. validate = full pipeline: Lint → Security →
Unit → Integration → Coverage → SonarScanner → Quality Gate → Smoke → Prometheus → Blackbox →
Grafana → Synthetic monitoring → Final report. sonar-init = idempotent SonarQube initialization.
observability-validate = monitoring + recovery checks without rebuilding everything. Every command:
correct exit codes.

# 19. IDEMPOTENCY AND RECOVERY — test all feasible scenarios, claim only executed ones:
A Fresh boot (`make bootstrap` on empty everything). B Second boot (reuse, no duplication).
C Normal restart (`down`→`up` recovers persistent state). D Invalid scanner token (revoke → safe
recovery via retained admin credentials). E Lost local token file (DB preserved → regenerate).
F Slow SonarQube startup (bounded polling with configurable timeout). G Interrupted bootstrap
(re-run resumes safely). H Chalice failure (Blackbox+Prometheus detect it). I Chalice recovery
(monitoring reports recovery). J Grafana restart (datasource/dashboards intact, no duplicates).
K Prometheus restart (TSDB samples survive). L Invalid monitoring config (promtool/compose validate
fail with meaningful diagnostics).

# 20. AWS DEPLOYMENT READINESS
Prepare (do NOT deploy, no credentials, no explicit authorization): `.chalice/config.json` with dev
and prod stages; least-privilege IAM recommendations (`chalice gen-policy` + review); deployment and
rollback instructions; logging strategy; CloudWatch integration guidance; metrics strategy (§13);
API Gateway considerations; Lambda cold-start considerations. Validate `chalice package --sam-template`
locally (works without credentials). Document local-vs-Lambda differences. Never claim AWS
deployment validated merely because the local API works.

# 21. CI/CD
GitHub Actions workflow: Lint, Security, Pytest, Coverage, SonarQube analysis, Quality Gate, Chalice
packaging. Do not assume public runners can reach this Mac's SonarQube — select and document the
preferred approach (self-hosted runner / ephemeral SonarQube in CI / network-accessible instance).
No automatic AWS deployment.

# 22. PROJECT STRUCTURE
Clean repository under the workspace root (adapt, justify changes):
```
observe/
├── app.py  chalicelib/{handlers,services,observability}/ chalicelib/{config,errors,logging,version}.py
├── .chalice/config.json  requirements.txt  requirements-dev.txt  pyproject.toml
├── tests/{unit,integration,contract}  conftest.py
├── docker/{chalice,sonar-scanner,bootstrap}/Dockerfile
├── monitoring/prometheus/{prometheus.yml,alerts.yml} monitoring/blackbox/blackbox.yml
├── monitoring/grafana/provisioning/{datasources,dashboards,alerting}/ monitoring/grafana/dashboards/
├── sonar/{bootstrap,configuration}/  sonar-project.properties
├── scripts/{bootstrap,validation,traffic}/
├── docs/{architecture,observability,testing,sonarqube,security,troubleshooting,aws-deployment}.md
├── .github/workflows/ci.yml
├── compose.yaml  Makefile  .env.example  .gitignore  README.md
```
Note: existing verified code lives at the root (`app.py`, `chalicelib/`, `pyproject.toml`) — extend,
don't rewrite from scratch.

# 23. DOCUMENTATION
Complete README: architecture + Mermaid diagram, requirements, installation, cold boot procedure,
service URLs, API examples, SonarQube authentication bootstrap, token storage + rotation, tests,
coverage reports, SonarScanner, Quality Gate, Prometheus, Blackbox, Grafana dashboards, alert
verification, traffic generation, failure simulation, recovery procedures, troubleshooting (must
include: scanner amd64-only limitation + ARM64 workaround, vm.max_map_count, slow first boot),
AWS readiness. Document exactly which processes run automatically. The user must not guess.

# 24. FINAL ACCEPTANCE TESTS (only check what was actually executed)
Infrastructure: compose valid · images build · containers start · healthchecks pass · volumes
persist. Chalice: API on configured port · /hello JSON · /health · /ready · error handling.
Testing: unit/integration/contract pass · 100% statement · 100% branch · reports generated.
SonarQube: cold start · admin initialized+authenticated · project · Quality Gate · project-scoped
token generated+securely stored · scanner auth works · real analysis computed · gate evaluated ·
repeated bootstrap idempotent. Prometheus: ready · config valid · targets UP · real samples · queries
recent. Blackbox: modules load · healthy probes succeed · content validated · failure detected ·
recovery detected. Grafana: starts · datasource provisioned+connectivity · dashboard created · PromQL
valid · real samples visible · no duplicates. Synthetic: normal/error/latency traffic · changes
visible · controlled failure detected · recovery observed. Security: no hardcoded creds · tokens
protected · secrets gitignored · checks execute · limited exposure. AWS: packaging works where
supported · deployment docs · IAM docs · local vs AWS differences explained.

# 25. FINAL EXECUTION REPORT
Print a real execution summary (template below; replace every value with actual results, and include
commands executed, exit codes, test evidence, real coverage %, real Quality Gate status, Prometheus/
Grafana verification, failed/skipped checks, remaining technical debt):

```text
==================================================
     AWS CHALICE DEVSECOPS LAB — FINAL STATUS
==================================================
ENVIRONMENT      Docker / Compose / Preflight: PASS/FAIL · Architecture: ARM64
APPLICATION      Chalice API / hello / health / readiness / error handling: PASS/FAIL
CODE QUALITY     Lint / Security / Pytest: PASS/FAIL · Statement: <actual %> · Branch: <actual %>
SONARQUBE        Cold boot / Bootstrap / Token validation / Analysis: PASS/FAIL · Quality Gate: <actual>
OBSERVABILITY    Prometheus / Blackbox / Grafana / Dashboards / Synthetic probes / Alerts: PASS/FAIL
END-TO-END       Traffic / Failure detection / Recovery / Idempotency: PASS/FAIL
VALIDATION SCOPE
  Local lab executed on macOS ARM64:  PASS / PARTIAL / FAIL
  AWS deployment:                     NOT EXECUTED (prepared only — local success does not prove Lambda/APIGW parity)
OVERALL RESULT: SUCCESS / FAILED / PARTIAL
==================================================
```

# 26. ENGINEERING PRINCIPLES
Infrastructure as Code · Configuration as Code · Observability as Code · Security by Design ·
Automated Testing · Reproducibility · Idempotency · Failure Recovery · Least Privilege ·
Production-relevant architecture · Simple maintainable solutions · Real end-to-end verification.
Avoid excessive complexity. Explain tradeoffs. Never silently skip requirements: if infeasible on
the selected edition, explain and implement the closest technically correct alternative.

# 27. EXECUTION INSTRUCTIONS
Work autonomously; do not stop at a plan. Execute the real workflow: inspect environment (reuse §1
verified data) → extend existing repo (API already implemented and smoke-tested) → tests →
Docker infra → SonarQube bootstrap + secure auth/tokens → Prometheus → Blackbox → Grafana →
alerting → traffic generation → Makefile orchestration → build → `make bootstrap` → diagnose/fix →
full validation → second bootstrap without deleting volumes → recovery scenarios → final report.
No approval needed for ordinary non-destructive steps. Explicit authorization required to deploy to
AWS, delete unrelated data, or change sensitive host settings. If the environment blocks something
(Docker, files, shell), state the exact limitation, commands attempted, and deliver the full
implementation without inventing validation results.

**FINAL OBJECTIVE:** a fully reproducible, self-initializing, secure, observable AWS Chalice
development platform demonstrating the complete DevSecOps lifecycle: empty local environment →
`make bootstrap` → working API, verified coverage, SonarQube Quality Gate, Prometheus monitoring,
Blackbox probes, Grafana dashboards, automated E2E validation. **Configuration files alone are not
enough: the objective is a functioning, tested and verified system.**
