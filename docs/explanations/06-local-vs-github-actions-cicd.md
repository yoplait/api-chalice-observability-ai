# Local "CI/CD" vs GitHub Actions CI/CD

The same pipeline runs in two places. This note explains what happens on your
laptop and exactly how the same thing maps onto GitHub Actions.

## 1. What "CI/CD" means here, plainly

**Continuous Integration** = on every change, automatically: build, lint, test,
measure coverage, analyze code quality, run a quality gate, smoke-test the
running app, run end-to-end tests. If any step fails, the change does not get
accepted.

**Continuous Delivery/Deployment** = if all that passes, you are one command
away from shipping (`make deploy`, and a git tag drives the GitHub release).

There is no magic: it is just a fixed sequence of commands that must each exit
with code 0.

## 2. The local pipeline

On your Mac, the pipeline runner is `make`. One command chains everything:

```
make validate
```

Internally that is, in order:

```
lint → test → coverage → sonar (scan) → quality-gate → smoke-test
       → observability-validate → e2e
```

Every stage is a Make target; every stage that can fail calls `exit 1`, and
because the chain is joined with `&&`, the first failure stops the whole thing
with a non-zero exit. That non-zero exit **is** the gate — locally a human
reads it; in CI it turns the run red and blocks the merge.

### How each stage runs locally

| Stage | What it actually runs | Where |
|-------|-----------------------|-------|
| lint | `ruff` / `black --check` / `bandit` | host venv |
| test + coverage | `pytest --cov`, writes `coverage.xml` | host venv |
| sonar (scan) | `docker compose run sonar-scanner` reading `coverage.xml` | `quality` network |
| quality-gate | `scripts/validation/quality_gate.sh` (waits for the scan's CE task, fetches measures, evaluates the gate, plus a local coverage guard) | host → `:9000` |
| smoke / e2e | `curl` + python scripts against `:8080` + `make start` stack | `app` network |

The Docker stack (`make start`) has to be up for the scan and the runtime
checks; `make validate` brings it up as needed. So "local CI" = your laptop +
Docker Compose + the Makefile as the orchestrator. Nothing is pushed to a
server; it is all ephemeral and repeatable (`make destroy` resets it).

### One fix worth knowing about

`quality_gate.sh` waits for the CE (background analysis) task to finish before
reading measures. There used to be a race: right after the scanner uploaded,
the new task was not yet in the queue, so the script saw the *previous* task as
`SUCCESS` and read stale measures (e.g. last run's coverage). It now snapshots
the last task id as a **baseline** and only trusts a *different* id reaching a
terminal state — so a bad commit is rejected on the very first gate run, no
re-run needed. If no fresh scan was submitted at all, it exits fast as `no-op`.

## 3. The same pipeline on GitHub Actions

GitHub Actions is just somebody else's machine that runs your steps when an
event fires (a push or a pull request). The steps are the same commands, put
into a YAML file under `.github/workflows/`.

### Trigger model

| Local | GitHub Actions |
|-------|----------------|
| you type `make validate` | `on: pull_request` (and/or `on: push`) |
| human sees red/green | commit status + PR check turns red/green |
| you decide not to merge | branch protection **blocks merge** if the check fails |
| `make deploy` / git tag | `on: push: tags: v*` (already wired: `github-release.yml`) |

The big behavioural difference is **branch protection**: in CI a failing
quality-gate check can be made mandatory, so the "bad commit" is physically
prevented from merging. Locally, the gate only blocks a human who obeys it.

### Two ways to get a SonarQube to scan against

**(A) Ephemeral SonarQube per run** — simplest, self-contained, no secrets
exposed outside the runner:

```yaml
name: CI
on: [pull_request]
jobs:
  quality:
    runs-on: ubuntu-latest
    services:
      sonarqube:
        image: sonarqube:community
        ports: ["9000:9000"]
        env: { SONAR_ES_BOOTSTRAP_CHECKS_DISABLE: "true" }
      postgres:
        image: postgres:16
        env: { POSTGRES_USER: sonar, POSTGRES_PASSWORD: sonar, POSTGRES_DB: sonar }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U sonar" --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"   # ruff, black, bandit, pytest, coverage
      - run: make lint test coverage    # produces coverage.xml
      - name: Wait for SonarQube
        run: |
          for i in $(seq 1 60); do
            curl -sf http://localhost:9000/api/system/status | grep -q '"status":"UP"' && break
            sleep 5
          done
      - name: Sonar scan
        uses: sonarsource/sonarqube-scan-action@master
        env: { SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}, SONAR_HOST_URL: http://localhost:9000 }
      - name: Quality gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        timeout-minutes: 5
        env: { SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}, SONAR_HOST_URL: http://localhost:9000 }
```

Because it is a brand-new SonarQube every run, you lose the shared "history"
and New Code period, but you get a fully reproducible gate. For the
Clean-As-You-Code "new code" conditions you'd want the community bootstrap to
recreate the gate first (your `make sonar-init` logic ported into a step), or
use option B.

**(B) Persistent shared SonarQube** — keep your real server (e.g. on a VM or a
long-lived container) and just point the scanner at it:

```yaml
      - name: Sonar scan
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_HOST_URL: https://sonar.internal.example
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

This is what teams use for real history, PR decoration and New-Code periods.
The downside: a self-hosted runner (or network access) is needed to reach a
private server.

### Secrets instead of `.sonar/token`

Locally the bootstrap writes the token to `.sonar/token`. In CI you never write
it to disk in the repo: store it once in **GitHub → Settings → Secrets** and
reference `${{ secrets.SONAR_TOKEN }}`. Same for `SONAR_HOST_URL`. Nothing
sensitive is committed — exactly the rule the local `sonar-project.properties`
already follows ("no token here").

### Reusing the Makefile

You don't have to rewrite the logic in YAML. A workflow can simply call the
same targets:

```yaml
    steps:
      - uses: actions/checkout@v4
      - run: make start          # bring up the compose stack
      - run: make validate       # the ENTIRE pipeline, one call
      - if: always()
        run: make destroy
```

This is the closest thing to "local CI" and keeps one source of truth (the
Makefile). The trade-off is it's all-or-nothing: GitHub can't show each stage
as a separate colored check, and the runner must support Docker Compose (a
standard `ubuntu-latest` runner does).

## 4. Local vs Actions — the honest differences

| | Local (`make`) | GitHub Actions |
|---|---|---|
| Trigger | a human types it | an event (`push`/`pull_request`) |
| Where it runs | your laptop + Docker | ephemeral GitHub VM / self-hosted runner |
| SonarQube | persistent container you own | ephemeral service *or* shared server |
| Gate enforcement | advisory (human obeys red) | **mandatory** via branch protection |
| Token | `.sonar/token` on disk | repo **Secrets** |
| Feedback | console text | PR comments, status checks, badges |
| Cost | your time + machine minutes | GitHub runner minutes |

The commands are identical; what changes is **who triggers them, where they
run, and whether a failure can actually stop a merge**. That last column is the
real point of CI.

## 5. Recommended path for this lab

1. Keep `make validate` as the single source of truth (it already is).
2. Add a `.github/workflows/ci.yml` that runs `make start && make validate &&
   make destroy` on `pull_request` — instant parity with local.
3. Later, split the Sonar stage into option A/B with a real token so PRs get
   quality-gate decoration, and turn on **branch protection → require the
   quality check**.

That gives you: local works → CI works → the gate actually blocks bad merges.
