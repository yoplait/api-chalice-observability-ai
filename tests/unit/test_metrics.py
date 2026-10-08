"""Unit tests: in-process metrics registry and Prometheus text rendering."""

from __future__ import annotations

from chalicelib.observability.metrics import (
    Counter,
    Histogram,
    MetricsRegistry,
    _escape,
    _fmt_labels,
)


def test_counter_render_cumulates_and_escapes():
    counter = Counter("test_total", "help", ("route",))
    counter.inc(("/hello",))
    counter.inc(("/hello",), 2.0)
    counter.inc(('/we"ird\n',), 1.0)
    out: list[str] = []
    counter.render(out)
    text = "\n".join(out)
    assert "# TYPE test_total counter" in text
    assert 'test_total{route="/hello"} 3.0' in text
    assert 'test_total{route="/we\\"ird\\n"} 1.0' in text


def test_histogram_cumulative_buckets_and_sums():
    hist = Histogram("dur", "help", ("route",), (0.1, 0.5, 1.0))
    hist.observe(("/x",), 0.05)
    hist.observe(("/x",), 0.7)
    out: list[str] = []
    hist.render(out)
    text = "\n".join(out)
    assert 'dur_bucket{route="/x",le="0.1"} 1' in text
    assert 'dur_bucket{route="/x",le="0.5"} 1' in text
    assert 'dur_bucket{route="/x",le="1"} 2' in text
    assert 'dur_count{route="/x"} 2' in text
    assert 'dur_sum{route="/x"} 0.75' in text


def test_registry_observe_request_status_classes():
    registry = MetricsRegistry()
    registry.observe_request("/hello", "GET", 200, 0.01)
    registry.observe_request("/hello", "GET", 503, 0.30)
    body = registry.render()
    assert "chalice_uptime_seconds" in body
    assert 'chalice_http_requests_total{route="/hello",method="GET",status="2xx"} 1.0' in body
    assert 'chalice_http_requests_total{route="/hello",method="GET",status="5xx"} 1.0' in body
    assert 'chalice_http_errors_total{route="/hello"} 1.0' in body
    assert body.endswith("\n")


def test_helpers():
    assert _fmt_labels(("a",), ("b",)) == '{a="b"}'
    assert _escape('x"\\y') == 'x\\"\\\\y'
