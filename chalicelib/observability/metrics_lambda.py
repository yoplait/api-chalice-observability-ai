"""CloudWatch (EMF) metrics backend for AWS Lambda.

This module is the *definitive* AWS deployment path described in
docs/observability.md. It is purely **additive**: locally nothing imports it at
runtime because `Config.metrics_backend` defaults to `"inproc"`, so the
in-process Prometheus registry (`metrics.py` + `/metrics`) is untouched and the
existing pull model (Prometheus scrape → Grafana) keeps working exactly as the
test suite expects.

Why a separate backend:
  * On Lambda there is no long-lived process to scrape: the microVM freezes
    after each invocation and `/metrics` counters in memory reset on cold
    starts. So we **push** one set of dimensions per request to CloudWatch
    using the Embedded Metric Format (EMF) via AWS Lambda Powertools.
  * CloudWatch then aggregates (Count / avg / p90 / Sum) server-side across all
    concurrent executions, which is exactly what the in-process Counter cannot
    do on Lambda.

To keep this importable on a plain dev machine (where `aws-lambda-powertools`
is not installed and is not needed), Powertools is imported lazily inside the
default factory, which is only exercised on real Lambda. In tests, inject a
fake metrics object via `configure()`.
"""

from __future__ import annotations

from typing import Protocol


class MetricsSink(Protocol):
    """The subset of AWS Lambda Powertools `Metrics` we depend on."""

    def add_metric(self, name: str, *, unit: str, value: float | int = 1, **dimensions: str) -> None: ...

    def flush_metrics(self) -> None: ...


_SINK: MetricsSink | None = None


def configure(sink: MetricsSink) -> None:
    """Inject the metrics sink. On Lambda the default factory is used instead;
    tests call this with a fake recorder so no AWS SDK is required."""
    global _SINK
    _SINK = sink


def _default_sink() -> MetricsSink:  # pragma: no cover - real Lambda only
    from aws_lambda_powertools import Metrics

    return Metrics(namespace="ChaliceLab", service="chalice-api")


def observe_request(route: str, method: str, status: int, duration: float) -> None:
    """Emit one request's dimensions to CloudWatch (EMF).

    Mirrors the labels of the in-process registry: route, method, status class.
    """
    sink = _SINK
    if sink is None:  # pragma: no cover - exercised only on real Lambda
        sink = _default_sink()
    status_class = f"{status // 100}xx"
    sink.add_metric(
        "http_requests",
        unit="Count",
        route=route,
        method=method,
        status=status_class,
    )
    sink.add_metric(
        "request_duration_ms",
        unit="Milliseconds",
        value=round(duration * 1000, 2),
        route=route,
        method=method,
    )
    if status >= 500:
        sink.add_metric("http_errors", unit="Count", route=route)


def flush() -> None:
    """Force the buffered EMF payload out to CloudWatch. Safe no-op when no
    sink is configured (e.g. the local in-process backend)."""
    if _SINK is not None:
        _SINK.flush_metrics()
