# Changelog

_Conventional Commits, orden **cronológico por día** (más reciente arriba); dentro de cada día: Features, Fixes, Chores, etc. Omite commits `chore(changelog):` (regeneración automática). Generador: **`scripts/generate_changelog.py`**._

## Releases (git tags)

Cada **`v*`** es una versión **semver** en Git; la fecha es la del **commit** al que apunta el tag.

- **`v0.7.0`** — 2026-10-21
- **`v0.6.0`** — 2026-10-21
- **`v0.5.0`** — 2026-10-20
- **`v0.4.0`** — 2026-10-20
- **`v0.3.0`** — 2026-10-19
- **`v0.2.0`** — 2026-10-13
- **`v0.1.0`** — 2026-10-08

## 2026-10-21

_**Versión(es) semver** etiquetada(s) con commit en esta fecha: `v0.7.0`, `v0.6.0`_

### Documentation
- update production paradigm to ECS containers only (`9eb7ac6`)
- finalize production paradigm (ECS containers, no X-Ray, no forced Lambda) (`c33b956`)

## 2026-10-20

_**Versión(es) semver** etiquetada(s) con commit en esta fecha: `v0.5.0`, `v0.4.0`_

### Documentation
- add quick local vs AWS Lambda comparison table (`4d7d131`)
- add production paradigm (ECS + CloudWatch) vs local lab (`467f4f1`)

## 2026-10-19

_**Versión(es) semver** etiquetada(s) con commit en esta fecha: `v0.3.0`_

### Features
- add CloudWatch (EMF) backend for AWS Lambda, fully additive (`0b69be9`)

### CI
- full-pipeline workflow + v0.3.0 (#1) (`85146c8`)

## 2026-10-16

### Fixes
- make quality gate CE-wait race-safe; add CI/CD explanation (`8c3fd53`)

## 2026-10-15

### Documentation
- add plain-English explanations for each component (`0ba309f`)

## 2026-10-13

_**Versión(es) semver** etiquetada(s) con commit en esta fecha: `v0.2.0`_

### Features
- external status-page incident monitoring + lifecycle fixes (`ac47535`)

### Documentation
- embed dashboard & quality-gate screenshots (`8fa0343`)
- fix architecture diagram + add credentials alias (`14e7941`)
- bare 'make' shows help; README architecture diagram rebuilt (`88641ca`)

## 2026-10-08

_**Versión(es) semver** etiquetada(s) con commit en esta fecha: `v0.1.0`_

### Features
- add release pipeline with changelog automation (`46ccb29`)

### Fixes
- update port references (Grafana 3001, API 8080) (`a3a40e0`)

### Documentation
- add architecture diagram to README (`1bff03d`)

### Other
- Initial commit: Chalice DevOps Lab (API, SonarQube, Prometheus, Grafana, monitoring) (`535ebfa`)
