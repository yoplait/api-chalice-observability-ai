# The SonarQube CI/CD flow — code quality as a gate

## The idea in one sentence

Every time code changes, a scanner analyzes it, sends the results to a server,
and the server decides **pass or fail** against a "Quality Gate". If it fails,
the pipeline stops — bad code never merges.

## The cast

| Piece | What it is | Where |
|-------|-----------|-------|
| **SonarQube** | the server: stores analysis, runs the Quality Gate | `:9000`, network `quality` |
| **sonarqube-db** | Postgres backing SonarQube's data | `:5432` (internal) |
| **sonar-scanner** | the client that reads the source and uploads a report | one-shot container |
| **sonar-bootstrap** | one-shot that creates project, gate, token, scanner user | first boot |
| **Quality Gate** | the pass/fail rule set (coverage, bugs, security…) | defined in SonarQube |

## The flow, step by step

```
   code
    │
    ▼
 sonar-scanner ──reads──► source + coverage.xml + test report
    │
    │ uploads an "analysis report"
    ▼
 SonarQube ──computes metrics──► stores them
    │
    │ compares metrics vs Quality Gate
    ▼
 verdict: OK or FAILED
    │
    ▼
 make quality-gate reads the verdict ──► exit 0 (pass) or exit 1 (block CI)
```

### 1. Bootstrap (once, on first boot)

`sonar-bootstrap` logs in, creates the project, creates the Quality Gate with
its conditions, makes a low-privilege `scanner` user and an analysis token, and
saves the secrets under `.sonar/` (never printed). It is idempotent — safe to
re-run.

### 2. Scan

`make sonar` runs the scanner container. It reads the code, the
`coverage.xml` (from `make coverage`) and the JUnit test report, then uploads a
report to SonarQube.

### 3. Compute

SonarQube processes the report in the background (a "CE task"). This takes a
few seconds — that is why the gate check waits for the task to finish.

### 4. Judge — the Quality Gate

The gate is a list of conditions. In this lab:

- `line_coverage` ≥ 100
- `branch_coverage` ≥ 100
- `duplicated_lines_density` ≤ 3
- `reliability_rating` ≤ A(1)
- `security_rating` ≤ A(1)
- plus Clean-As-You-Code conditions on *new* code

### 5. Block or pass

`make quality-gate` asks SonarQube for the verdict. The script
(`scripts/validation/quality_gate.sh`) waits for the analysis to finish, then
checks each condition. Any failure → non-zero exit → the CI pipeline fails and
the merge is blocked.

## A quirk of the Community edition

The free SonarQube only returns the **Clean-As-You-Code** conditions through
the `project_status` API. The "overall" conditions are not all reported. So the
script **re-evaluates the full gate locally**: it reads the gate definition
(`/api/qualitygates/show`), fetches the project's measures
(`/api/measures/component`), and applies the operators itself. That is why you
will see conditions marked `SKIP (no Cayc baseline)` — there is no previous
version to compare new code against yet.

## Where this runs today

Right now the gate runs **locally** via `make validate` (which chains
lint → test → coverage → `make sonar` → `make quality-gate` → smoke → e2e).
The repo's GitHub Actions currently only automate the changelog and the release
(`.github/workflows/changelog.yml`, `github-release.yml`); they do **not** yet
run the quality gate.

To make it a real merge gate, add a CI workflow that runs `make sonar` and
`make quality-gate` on every pull request — the gate's non-zero exit is what
would block the merge. That step is intentionally left as a follow-up.


## One-line summary

SonarQube turns "is this code good enough?" into a yes/no the pipeline obeys:
scan → analyze → judge against the Quality Gate → pass or block the merge.
