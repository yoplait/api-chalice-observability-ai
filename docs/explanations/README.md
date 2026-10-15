# Plain-English Explanations

Short, jargon-free notes on what each moving part of this lab is and does.
Written for someone who wants the mental model first, the details second.

| File | Topic |
|------|-------|
| [01-what-is-an-exporter.md](01-what-is-an-exporter.md) | What an "exporter" is, and the two we use |
| [02-prometheus.md](02-prometheus.md) | The time-series database and how scraping works |
| [03-grafana.md](03-grafana.md) | The visualization layer |
| [04-the-api.md](04-the-api.md) | What the Chalice API is and its endpoints |
| [05-sonar-cicd-flow.md](05-sonar-cicd-flow.md) | The code-quality CI/CD flow with SonarQube |

Rule of thumb used everywhere: **collect → store → show**.
Exporters collect, Prometheus stores, Grafana shows. SonarQube is a separate
"collect → judge → block" pipeline for code quality.
