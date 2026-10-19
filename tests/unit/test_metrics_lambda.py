"""Unit tests: CloudWatch (EMF) metrics backend for the AWS Lambda path.

No AWS SDK is imported: we inject a fake sink via configure(), which mirrors
the small slice of Powertools' Metrics API we rely on (add_metric/flush_metrics).
"""

from __future__ import annotations

import pytest

from chalicelib.observability import metrics_lambda


class FakeSink:
    def __init__(self):
        self.metrics: list[tuple] = []
        self.flushes = 0

    def add_metric(self, name, *, unit, value=1, **dimensions):
        self.metrics.append((name, unit, value, dimensions))

    def flush_metrics(self):
        self.flushes += 1


@pytest.fixture(autouse=True)
def reset_sink():
    metrics_lambda._SINK = None
    yield
    metrics_lambda._SINK = None


def test_configure_injects_sink():
    sink = FakeSink()
    metrics_lambda.configure(sink)
    assert metrics_lambda._SINK is sink


def test_observe_request_success_path():
    sink = FakeSink()
    metrics_lambda.configure(sink)
    metrics_lambda.observe_request("/hello", "GET", 200, 0.123)
    names = [m[0] for m in sink.metrics]
    assert names == ["http_requests", "request_duration_ms"]
    req = sink.metrics[0]
    assert req[3] == {"route": "/hello", "method": "GET", "status": "2xx"}
    dur = sink.metrics[1]
    assert dur[2] == 123.0  # duration_ms, rounded
    assert dur[3] == {"route": "/hello", "method": "GET"}


def test_observe_request_error_path_emits_errors():
    sink = FakeSink()
    metrics_lambda.configure(sink)
    metrics_lambda.observe_request("/boom", "POST", 503, 0.05)
    names = [m[0] for m in sink.metrics]
    assert "http_errors" in names
    assert sink.metrics[0][3]["status"] == "5xx"


def test_flush_calls_sink_when_configured():
    sink = FakeSink()
    metrics_lambda.configure(sink)
    metrics_lambda.flush()
    assert sink.flushes == 1


def test_flush_is_noop_without_sink():
    # No sink configured -> flush must not raise and does nothing.
    metrics_lambda.flush()
