# Revisión del MASTER PROMPT — verificación contra el entorno real (2026-10-08)

## Veredicto
El prompt está bien integrado y cubre los 4 detalles finales (healthchecks, credenciales,
recuperación, limpieza/repetibilidad) y la distinción local vs AWS (§20). Tiene
**6 correcciones necesarias** antes de pasarlo a Codex; todo lo demás es opcional.

## Correcciones (obligatorias)

### 1. §1 — La ruta sigue siendo un placeholder
`RUTA_LOCAL_DEL_PROYECTO` no se ha sustituido. Reemplazar por:
`/Users/perezpardojc/Documents/code/nan/observe`

### 2. §4/§11 — SonarScanner: la imagen oficial NO tiene ARM64 (verificado)
- `docker buildx imagetools inspect sonarsource/sonar-scanner-cli:latest` → imagen única, sin manifiesto multi-arq.
- Tags en Hub (API `/v2/repositories/.../tags`): **todos** `amd64`.
- Ejecutarla bajo emulación amd64 en este host **crashea** el launcher nativo:
  `assertion failed [hash_table != nullptr]: Failed to find vdso DT_HASH` (inclusión con `--entrypoint sh`).
- **Workaround verificado**: dentro de la imagen, `bin/sonar-scanner` es un script POSIX sh (`#!/usr/bin/env sh`, invoca `java`) y `lib/sonar-scanner-cli-8.1.0.6389.jar` es bytecode portable. Solución: `docker cp` del directorio `/opt/sonar-scanner` completo a una imagen propia ARM64 (base JRE 17+, p. ej. `eclipse-temurin:21-jre`). Añadir esto como nota en §4 y fijar la versión del scanner (p. ej. `8.1.0`) + pin por digest del upstream.

### 3. §3 — Chalice 1.33 cambió la API de extensiones (verificado en 1.33.0)
- Eliminados `@app.before_request` / `@app.after_request` / `@app.error_handler`; solo existe `@app.middleware("http")`.
- Los `ChaliceViewError` NO llegan al middleware (el framework los convierte dentro de la vista); para que una excepción escape al middleware hay que lanzar `ChaliceUnhandledError`.
- Los query params no se coercitan a los tipos del firm de la vista: siempre llegan `str`; la validación/conversión debe ser explícita.
- `Blueprint(__name__)` de 1 param y `app.register_blueprint()` (no `app.blueprint()`).
- Añadir estas 4 notas al final de §3 (ahorran a Codex ~1 hora de depuración).

### 4. §4/§6 — Fijar PostgreSQL 16/17
Community Build actual ya no soporta PG < 14/15 según versión. Concretar `postgres:16-alpine` (ARM64 verificado OK) en §4, y la nota de `vm.max_map_count` de §1 debe mencionar el truco del contenedor privileged one-shot en Docker Desktop (no tocar el host sin autorización, ya está bien).

### 5. §7 — Matiz del primer arranque de SonarQube (gotcha real)
`/api/system/status == UP` puede producirse con credenciales todavía bloqueadas por el flujo de inicialización de seguridad. El bootstrap debe esperar a `UP` **y** validar que la autenticación funciona antes de continuar (intento de `/api/projects/search` con credenciales). El prompt ya dice "verify that authentication works" en el punto 6, pero conviene atarlo explícitamente al gating del readiness en §6/§7 para que Codex no ordene mal los pasos.

### 6. §25 — Añadir fila explícita "Local vs AWS" al informe final
```text
VALIDATION SCOPE
  Local lab executed on macOS ARM64:  PASS/FAIL/PARTIAL
  AWS deployment executed:            NOT EXECUTED (prepared only)
```
§20 lo pide como comportamiento; §25 debe exigir reportarlo como campo visible.

## Ajustes opcionales (menores)
- §1 dice "Docker Compose v2"; este host reporta Compose `v5.3.1`. Escribir "Compose v2+ (`docker compose`)".
- §6: timeout de 300 s es razonable; añadir nota de primer arranque lento (~2-4 min en VM Docker de 8 GiB; 4 CPU/8 GiB verificados con `docker info`).
- §9: añadir generación de `junit.xml` explícita (`--junitxml`) porque §9 lo pide y conviene fijarlo en la imagen `tests`.
- §8: recordar que "100% statement/branch" lo gatea `coverage.py fail_under=100`; en Sonar Community no existe condition de branch-coverage nativa → el pipeline local es quien lo enforce (el prompt ya lo cubre, pero queda más claro con un ejemplo de metric name real: `coverage.xml` → `Line coverage`; `Lines to Cover` puede verse afectado por excluidos).
- §13/§7 (app metrics): el `REGISTRY` in-process por middleware se pierde en cold start Lambda; §13 ya lo documenta bien.

## Reclamos del prompt verificados como CIERTOS
- SonarQube `sonarqube:community` corre nativo ARM64 (pull + inspect: `arm64`). OK, como dices.
- Grafana 12.1.1, Prometheus v3.7.3, Blackbox v0.27.0, postgres:16-alpine, alpine:3.20: todos ARM64 nativo.
- chalice 1.33.0 sobre Python 3.12.13: instalado y API funcionando (routes + middleware + test client verificados).
- Sin imágenes de pago: todo lo listado es OSS.

## Estado del repo a fecha de esta revisión
Implementación parcial ya existente en el workspace: `app.py`, `chalicelib/` (config, logging JSON,
errors/handler de vistas, metrics in-process, middleware pipeline, handlers core/demo),
`pyproject.toml`, smoke Test-Client en verde. Falta: tests pytest, compose, monitoring/,
sonar/, scripts/, Makefile, CI, docs, y la ejecución de bootstrap (§5).
