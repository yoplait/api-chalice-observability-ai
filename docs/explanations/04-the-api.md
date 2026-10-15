# The Chalice API — what it is

## What it is

It is a small HTTP web service written with AWS **Chalice** (Python). It is the
"application under test" of this lab — the thing all the monitoring watches.
It does nothing business-critical on purpose; its job is to be a realistic
target that can be healthy, slow, or failing so the observability stack has
something to observe.

Inside Docker it listens on port **8000**; the host sees it on **8080**.

## The endpoints

| Route | What it returns | Why it exists here |
|-------|-----------------|--------------------|
| `GET /` | index | liveness |
| `GET /health` | `{"status":"ok"}` | deep health check (blackbox probes this) |
| `GET /ready` | `{"status":"ready"}` | readiness (is it safe to send traffic?) |
| `GET /hello` / `GET /hello?name=X` | greeting | normal happy-path request |
| `GET /version` | build version | release info |
| `GET /metrics` | Prometheus text | the app's own internal metrics |
| `GET /greet?name=X` | greeting | parameter handling |
| `GET /demo/bad_request` | 400 | controlled client error |
| `GET /demo/unavailable` | 503 | controlled server error |
| `GET /demo/exception` | 500 | controlled crash path |
| `GET /demo/slow?ms=N` | delayed 200 | controlled latency |

The `/demo/*` routes are deliberate failure/slow knobs. The end-to-end test
uses them to prove Prometheus + blackbox actually detect errors and latency.

## Two kinds of metrics from the API

This is a subtle but important point:

- **Internal metrics** — the app itself counts its own requests, errors and
  latency and exposes them at `/metrics`. Prometheus scrapes them.
  ("from the inside, how many 5xx did I serve?")
- **External probes** — the blackbox-exporter hits `/health` etc. from outside
  and records success/latency. ("from the outside, did it answer in time?")

Both feed the Observability dashboard. If the two disagree (the app says it is
fine but the probe times out), that itself is a signal.

## Try it

```bash
curl http://localhost:8080/health
curl http://localhost:8080/hello?name=world
curl http://localhost:8080/metrics | head
curl http://localhost:8080/demo/unavailable   # returns 503 on purpose
```

## One-line summary

The Chalice API is a deliberately simple web service whose only real purpose is
to be monitored, load-tested and broken in controlled ways so the pipeline
around it can be demonstrated.
