# MASTER PROMPT — Laboratorio DevOps AWS Chalice (chalice-devops-lab)

## ROL
Actúa como Senior DevOps Engineer, AWS Solutions Architect, SRE y Python Software Engineer.
Genera el laboratorio **real, ejecutable y verificado**: archivos, contenedores, ejecución de pruebas y evidencia de resultados. No pseudocódigo, no simulaciones, no métricas inventadas.

## 0. ENTORNO VERIFICADO (datos reales de esta máquina — macOS 14.8.5 Apple Silicon arm64)
- Docker Engine 29.5.3 linux/arm64, Docker Compose v5.3.1. VM de Docker Desktop: **4 CPUs / 8 GiB**. Diseña los límites de memoria de SonarQube (+PostgreSQL), Prometheus, Grafana y la API para caber en ese presupuesto (~3 GiB en steady state); documenta el cálculo.
- Python 3.12.13 disponible (`/opt/homebrew/bin/python3.12`). `chalice==1.33.0` instalado y funcional con Python 3.12.
- Imagenes **nativas ARM64 verificadas** (sin emulación): `sonarqube:community`, `grafana/grafana:12.1.1`, `prom/prometheus:v3.7.3`, `prom/blackbox-exporter:v0.27.0`, `postgres:16-alpine`, `alpine:3.20`.
- **Restricción conocida**: la imagen oficial `sonarsource/sonar-scanner-cli` **solo publica amd64** y la emulación amd64 falla en este host (crash del runtime nativo). Solución obligatoria: imagen propia `docker/sonar-scanner/Dockerfile` ARM64 (p. ej. `eclipse-temurin:21-jre` + zip oficial `sonar-scanner-cli-<versión>.zip` descargado en build-time con GET a binaries.sonarsource.com, versión fijada con su checksum), o como fallback ejecutar el scanner dentro de la imagen `tests`. Documenta la limitación elegida y por qué.
- **Restricción conocida de Chalice 1.33**: se eliminaron `@app.before_request`, `@app.after_request` y `@app.error_handler`. La observabilidad y el manejo centralizado de errores deben implementarse con `@app.middleware("http")`. Los `ChaliceViewError` se convierten a respuesta dentro del framework y **no** llegan al middleware; para que una excepción llegue al middleware usa `ChaliceUnhandledError`. Los parámetros de query NO se coercitan automáticamente (reciben `str`): valida y convierte explícitamente.

## 1. WORKSPACE
Directorio de trabajo exclusivo: `/Users/perezpardojc/Documents/code/nan/observe`.
Todo debe arrancar con Docker Compose. La API corre localmente con `chalice local`, conservando estructura nativa para desplegar después en Lambda + API Gateway. Sin credenciales AWS locales.

## 2. OBJETIVO Y ARQUITECTURA
API Hello World + plataforma completa de calidad y observabilidad:

```
LOCAL DEVOPS LAB
├── AWS Chalice REST API ──► /hello /health /ready /version /demo/*
│        └── métricas internas (middleware) ──► /metrics (solo local; ver §7)
├── Quality Pipeline ──► pytest+coverage ──► SonarQube Community ──► Quality Gate
└── HTTP Monitoring ──► Blackbox Exporter ──► Prometheus ──► Grafana (dashboards+alertas)
```

## 3. AWS CHALICE API
Endpoints obligatorios: `GET /` (info API), `GET /hello` (hello world JSON), `GET /health` (liveness, sin dependencias externas), `GET /ready` (readiness honesta), `GET /version` (versión+entorno), `GET /demo/error` (error controlado), `GET /demo/slow` (latencia controlada).

Requisitos: respuestas JSON consistentes (envelope único), códigos HTTP correctos, separación rutas/lógica de negocio (`chalicelib/handlers` + `chalicelib/services`), configuración por variables de entorno (`chalicelib/config.py`, validación estricta, sin secretos en código), logging estructurado JSON con correlation ID (header `X-Correlation-Id` entrante o generado), manejo centralizado de errores vía middleware (mapea errores de dominio a JSON 4xx/5xx; los 5xx inesperados loguean `exc_info`), validación de entradas explícita, dependencias fijadas (`requirements.txt` con versiones verificadas).
`/demo/*` queda **hard-deshabilitado cuando `APP_STAGE=prod`** (aunque la env var de habilitación esté mal puesta a true: la config debe forzarlo).

## 4. DOCKER COMPOSE (`compose.yaml`)
Servicios: `chalice-api`, `prometheus`, `blackbox-exporter`, `grafana`, `sonarqube`, `sonarqube-db` (postgres:16-alpine), `sonar-bootstrap` (one-shot, perfil `quality`), `sonar-scanner` (one-shot, perfil `quality`), `tests` (one-shot, perfil `test`), `traffic-generator` (perfil `traffic`).

Incluye: Dockerfiles versionados, redes internas (frontend/backend), volúmenes persistentes nombrados, `.env` (chmod 600) + `.env.example`, pinned tags de imágenes.

**Healthchecks y dependencias (crítico)**: Ningún servicio puede considerarse "listo" solo por estar arrancado.
- Healthchecks reales por endpoint: API `GET /health`; SonarQube `GET /api/system/status == UP`; PostgreSQL `pg_isready`; Prometheus y Blackbox `GET /-/ready`; Grafana `GET /api/health`.
- `depends_on` con `condition: service_healthy` encadenando: db→sonarqube→bootstrap→scanner; api→blackbox→prometheus→grafana.
- `restart: unless-stopped` en servicios long-running; `no` en one-shots.
- API accesible desde el host en el puerto definido en `.env`.

## 5. TESTING Y COVERAGE (pytest)
Tests unitarios, de integración (Test client / LocalGateway de Chalice o middleware directo), contract/API (esquema JSON de cada respuesta), healthcheck, manejo de errores, casos positivos y negativos. Usa `chalice.test.Client` cuando sea posible y HTTP real contra `chalice local` para contract tests.
Objetivo: **100% statement + 100% branch coverage** del código propio (`app.py`, `chalicelib/**`), con `fail_under=100` en `pyproject.toml`. Sin tests artificiales: si algo es genuinamente inalcanzable, exclúyelo con justificación escrita.
Genera: reporte consola, `htmlcov/`, `coverage.xml` (Cobertura para Sonar) y evidencia en `docs/evidence/`.
Servicio `tests`: ejecuta pytest + coverage en contenedor, deja los artefactos en bind mounts y devuelve exit code != 0 si falla.

## 6. SONARQUBE + BOOTSTRAP AUTOMATIZADO
SonarQube **Community** (`sonarqube:community`) con PostgreSQL. Proyecto `chalice-devops-lab`. Cobertura desde `coverage.xml`, detección de duplicados, bugs, hotspots. Quality Gate personalizado: cobertura propio 100%, duplicaciones < 3%, 0 issues altos nuevos, 0 vulnerabilidades, 0 bugs bloqueantes. (Si alguna condición no es configurable en Community, aplícala en `quality-gate.sh` y documenta la limitación real.)

**Cold start**: `sonar-bootstrap` es un servicio one-shot que:
1. Espera con polling real a `/api/system/status == UP` (timeout configurable, reintentos; no confiar en `depends_on`, en que el puerto abra, ni en sleeps fijos).
2. Resuelve el desbloqueo administrativo de primer arranque de forma idempotente (cambio de password admin solo si aplica; soporta instancia ya configurada).
3. Crea el proyecto si no existe; crea y asigna el Quality Gate y sus condiciones; configura permisos de análisis (usuario/`token` con rol `scanner`/`codeviewer` en el proyecto).
4. Genera un token de proyecto y lo persiste en archivo fuera de Git (p. ej. `.sonar/token` con `chmod 600`, gitignoreado; o en el keychain). Nunca imprime el token (ni en logs, ni en `ps`, ni en `docker compose logs`): pasar a contenedores únicamente vía `SONAR_TOKEN` en environment de compose, nunca en `sonar-project.properties` versionado.
5. Revalida el token existente al relanzar (`/api/user_tokens/search` o `/api/session/do_not_disturb` con el token); si es inválido/revocado, regenera. Rotación explícita con `make sonar-rotate-token`.
6. Ante un fallo parcial (p. ej. proyecto creado pero token no generado), la reejecución debe continuar desde donde falló sin duplicar nada.
7. Si algo falla, vuelca logs de `sonarqube`/`sonarqube-db` con `docker compose logs --tail` y termina != 0.

**Flujo de análisis** (`make sonar` / `make quality-gate`): tests → coverage.xml → bootstrap → scanner (espera finishing) → sonar-scanner → esperar `POST /api/analysis_reports/is_queue_empty` y `computed=false` → consultar `GET /api/qualitygates/project_status` → exit != 0 si no supera. El éxito del proceso scanner **no** implica Quality Gate superado.

Escenarios de aceptación a ejecutar y documentar: 1) primer arranque desde cero; 2) segundo arranque con volúmenes; 3) reinicio de SonarQube; 4) token inválido/revocado; 5) PostgreSQL caído temporalmente; 6) arranque lento de SonarQube; 7) bootstrap interrumpido y reejecutado.

## 7. PROMETHEUS + BLACKBOX + MÉTRICAS DE APLICACIÓN
- `promtool check config` y `check rules` en validate.
- Scrape cada 15s. Jobs: blackbox sobre `/health`, `/ready`, `/hello`, `/version`; `prometheus`; y la API vía `/metrics` **solo en local**.
- Módulos HTTP de blackbox con validación de status code Y contenido JSON esperado (JSONPath/regex), timeout por sonda, `preferred_ip_protocol: ip4`. Targets con DNS de red compose (nunca `localhost`), etiqueta `endpoint` por sonda.
- Alertas: API-Down, Readiness-Failed, High-Response-Time, HTTP-Errors, Monitoring-Target-Missing (distinguiendo fallo de API vs fallo del monitor).
- Métricas internas de app (requests/s, latencia por endpoint, errores, distribución de códigos) desde el middleware Chalice con registro thread-safe: expose en `/metrics` para el scrape local. **No presentar sondas blackbox como métricas de todas las peticiones.** Documentar la estrategia serverless: en Lambda no hay proceso persistente ni scrape → migración a CloudWatch EMF / OpenTelemetry Lambda (instrucciones en `docs/observability.md`).

## 8. GRAFANA (provisioning automático)
DataSource Prometheus con UID fijo, carpeta `Chalice Observability`, dashboard **AWS Chalice API — Observability** versionado en `monitoring/grafana/dashboards/*.json` con paneles y PromQL reales: Availability, Health Status, Readiness Status, Response Time, HTTP Status Codes, Probe Success Rate, Endpoint Comparison, Monitoring Target Health. Alertas Grafana donde aplique (compatibles con la versión 12.x instalada).
Credenciales: admin inicial desde `.env`/secret file (no hardcodeado en Git), persistido por el volumen `grafana-data`; documentar rotación (`make grafana-change-password`).
Verificación por API (no solo importar el JSON): datasource existe, `POST /api/datasources/.../health` contra Prometheus OK, dashboard presente, queries de paneles devuelven series recientes (`/api/datasources/proxy/uid/.../api/v1/query_range`).

## 9. SYNTHETIC TRAFFIC GENERATOR
`scripts/traffic_generator.py` (stdlib) en servicio opcional perfil `traffic`: modo normal (rps configurable a `/hello`), modo degradado (`make traffic-errors`: activa `/demo/slow` y `/demo/error` controlados), arrancable/parable por perfil/env. Nunca ataca endpoints demo si `APP_STAGE=prod`. Sirve para ver mover los dashboards.

## 10. PRUEBAS DE RECUPERACIÓN (obligatorias y documentadas)
- `make chaos` ejecuta y verifica con evidencia:
  1) API caída (`docker compose stop chalice-api`): Prometheus dispara API-Down; al arrancar, todo se recupera sin reiniciar el resto.
  2) Latencia elevada (traffic-errors): alerta/panel de High-Response-Time refleja el aumento real.
  3) Reinicio de cada servicio (restart policies): los dashboards y consultas se recuperan.
  4) Pérdida temporal de red (pausar contenedor API unos minutos y reanudar).
  5) Recalentamiento con volúmenes persistidos: `make up` no reintroduce estado duplicado.
Considera `evaluation_interval` + `for:` al afirmar que una alerta llegó a `firing` (una caída breve no es alerta firing: documenta tiempos observados).

## 11. LIMPIEZA Y REPETIBILIDAD
`make bootstrap` debe poder ejecutarse N veces sobre el mismo estado (con volúmenes vacíos o poblados) sin duplicar configuraciones ni credenciales: todo step es idempotente y verificable.
`make destroy` (o `make clean`) baja contenedores, **borra volúmenes** y artifacts de análisis, y deja el repo listo para un `make bootstrap` desde cero limpio. `.gitignore` completo (incluye `.env`, `.sonar/`, `htmlcov/`, `coverage.xml`, `.pytest_cache/`, `site/`, `.chalice/` artifacts).

## 12. MAKEFILE / ORQUESTACIÓN
`make help up down clean destroy status logs test coverage lint security format sonar sonar-rotate-token quality-gate smoke-test traffic traffic-errors chaos observability-validate aws-package validate bootstrap`
- `make bootstrap` = orquestador completo con timeouts, reintentos, logs útiles, exit codes correctos y **final report** PASS/FAIL por componente: preflight (docker/python/recursos/versiones) → build → infra up con healthchecks → Sonar bootstrap → tests+coverage → scanner+quality gate → prometheus ready + targets UP + `probe_success=1` por endpoint (consultas reales a `/api/v1/targets` y `/api/v1/query`) → grafana provisioning verificado → tráfico sintético → verificación e2e → reporte.
- `make observability-validate` = solo §7/§8 checks.
- `scripts/verify-observability.sh`: 1) curl API `/health` `/hello`; 2) sondas blackbox directas `/probe`; 3) series en Prometheus (`probe_success`, `probe_duration_seconds`); 4) API Grafana (datasource+dashboard+queries con datos); 5) generar tráfico y ver muestras nuevas; 6) caída temporal y recuperación (restaurando SIEMPRE el estado, incluso al fallar el script: `trap`/cleanup).
- `make validate` = lint → security → unit → integration → coverage ≥ objetivo → SonarScanner → Quality Gate real → smoke tests → verificación de monitoring. Cualquier etapa fallida ⇒ exit != 0.

## 13. SECURITY & CODE QUALITY
Ruff, Black, Bandit (noff con justificación documentada, no silencios vacíos), pip-audit sobre requirements fijados, contenedores no-root cuando sea viable, sin secretos en Git (política documentada), imágenes con tag pinned. Distinguir findings reales de limitaciones de cada herramienta.

## 14. AWS DEPLOYMENT READINESS (preparar; NO desplegar)
`.chalice/config.json` con stages dev/prod (variables, `api_gateway_stage`, IAM **policies mínimas** generadas con `chalice gen-policy` + revisión), `requirements.txt` para Lambda, instrucciones `chalice deploy`/`chalice package --sam-template` y validación offline del paquete (SAM template + zip inspeccionado, sin cuenta AWS), estrategia de logs/métricas en AWS (CloudWatch, OTel), rollback (aliases/versiones), diferencias observabilidad local vs AWS. **Prohibido usar credenciales reales o desplegar.**

## 15. ESTRUCTURA DEL REPOSITORIO
```
observe/ (chalice-devops-lab)
├── app.py  chalicelib/{config,errors,logging}.py chalicelib/handlers/ chalicelib/services/ chalicelib/observability/{pipeline,metrics}.py
├── .chalice/config.json  requirements.txt  pyproject.toml
├── tests/{unit,integration,contract}  conftest.py
├── docker/{chalice,sonar-scanner,bootstrap}/Dockerfile  scripts/
├── monitoring/{prometheus/,blackbox/,grafana/{provisioning/,dashboards/}}
├── sonar/ (si aplica)  sonar-project.properties (sin token)
├── .github/workflows/ci.yml
├── compose.yaml  Makefile  .env.example  .gitignore
├── docs/{architecture,observability,testing,aws-deployment,recovery-tests,evidence/}.md
└── README.md
```

## 16. CI/CD (ejemplo, no se ejecuta contra este Mac)
GitHub Actions: lint → security → pytest+coverage → SonarQube (temporal en runner o auto-hosted) → Quality Gate poll → `chalice package` + validación de artefactos. Explicar que un runner público **no puede** alcanzar el `localhost` del Mac. Sin publicar imágenes ni desplegar por defecto.

## 17. DOCUMENTACIÓN
README profesional: descripción, diagrama Mermaid, pre-requisitos, quick start (`cp .env.example .env && make bootstrap`), URLs/puertos, ejemplos curl, tabla de comandos make, uso de SonarQube y consulta de cobertura, Grafana, tráfico, simulación de errores, troubleshooting (incl. vm.max_map_count si Elasticsearch lo exigiera y la restricción amd64 del scanner oficial), preparación AWS. Documento `docs/pipeline.md`: Developer → Git → Tests → Coverage → Sonar → Quality Gate → Deploy → Monitoring → Alerts.

## 18. CRITERIOS DE ACEPTACIÓN (marcar solo lo comprobado con evidencia)
[ ] `make up` levanta la plataforma con healthchecks verdes · [ ] API responde HTTP · [ ] `/hello` JSON esperado · [ ] `/health`+`/ready` OK · [ ] pytest completo en verde · [ ] 100% statement+branch propio · [ ] SonarQube UP · [ ] scanner envía análisis · [ ] **Quality Gate: resultado real consultado por API** · [ ] targets Prometheus UP · [ ] blackbox: `probe_success=1` en los 4 endpoints · [ ] Grafana con datasource+dashboard verificados por API y datos reales · [ ] traffic generator funciona · [ ] caída simulada detectada (alerta firing tras su `for:`) · [ ] latencia elevada detectada · [ ] 7 escenarios bootstrap Sonar superados · [ ] recuperación: reinicios/caída/red verificados · [ ] `make bootstrap` reejecutado 2 veces con mismo resultado · [ ] `make destroy && make bootstrap` parte de cero · [ ] documentación coherente con lo ejecutado.

## 19. ENTREGA FINAL
1. Tabla: `| Componente | Estado | Verificación (comando+salida) | URL |` para Chalice API, Pytest, Coverage, SonarQube, Quality Gate, Prometheus, Blackbox, Grafana, Traffic, Bootstrap.
2. Sección **"Local validado" vs "AWS preparado (no ejecutado)"** explícita: el laboratorio local demuestra la API bajo `chalice local`; probar `chalice package/deploy` en Lambda+API Gateway con comportamiento idéntico **no** se ha ejecutado aquí y debe listarse como pendiente de validación en cuenta AWS real (menciona qué cambia: middleware OK, sin scrape `/metrics`, cold starts, timeouts).
3. Bloqueos documentados con comando exacto y workaround propuesto.
4. Nunca dar por bueno un resultado que no se haya ejecutado en esta máquina.
