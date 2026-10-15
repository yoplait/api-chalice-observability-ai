# What is an exporter?

## The plain idea

Prometheus can only read one thing: a plain-text page full of numbers, served
at a URL that usually ends in `/metrics`. It looks like this:

```
http_requests_total 1027
probe_success 1
external_status_incidents_active 3
```

Most real systems do **not** speak that language. A web server, a database, or
Okta's status page each have their own format. An **exporter** is a small
program that sits in the middle:

1. It looks at some system.
2. It converts what it sees into the number-page format.
3. It serves that page at a URL so Prometheus can come and pick it up.

Analogy: Prometheus is an electrician who only reads electricity meters. An
exporter is the meter you bolt onto something that never had one (a water tap,
a room's temperature, a third-party outage feed).

## The two exporters in this lab

### blackbox-exporter — watches *our* API, from the outside

- Official image `prom/blackbox-exporter`, port 9115.
- It does not read the API's internals. It does what a real user would:
  "open `http://chalice-api:8000/health`, did it answer, and how long did it take?"
- Because it probes from **outside**, it catches cases the API's own metrics
  cannot: the process is up but the route is broken, the container is alive but
  the HTTP layer is stuck, etc.
- Output metrics: `probe_success` (1/0), `probe_http_duration_seconds`,
  `probe_http_status_code`.
- "Black box" = it does not care what is inside, only what goes in and comes out.

### statuspage-exporter — watches *other people's* services

- Our own script: `scripts/exporters/statuspage_exporter.py`, port 9118.
- It polls the public status pages of Okta, Twilio, GitHub, Stripe and Google,
  reads whether they have open incidents, and turns that into numbers:

  ```
  external_status_incidents_active{service="twilio"} 3
  external_status_up{service="stripe"} 0
  ```

- This is how a third-party outage (e.g. "Okta had an issue in EMEA last night")
  shows up **red** in our dashboard even though our own API is perfectly fine.
- "Status page" = it reads the public status pages of other providers.

## Why two, and how they differ

| | blackbox-exporter | statuspage-exporter |
|---|---|---|
| Watches | our own API | other companies' services |
| Method | HTTP probe (is it up? how fast?) | read their status API/HTML |
| Tells you | "our endpoint is healthy" | "a dependency is having an incident" |
| Image | official | our script |

Same concept, different target. Each Grafana dashboard maps to one of them:
the Observability dashboard uses blackbox, the External Status Pages dashboard
uses statuspage.
