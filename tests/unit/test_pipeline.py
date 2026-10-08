"""Unit tests: observability middleware (correlation ids, metrics, failure path)."""

from __future__ import annotations

import pytest

from chalicelib.observability import pipeline
from chalicelib.observability.metrics import REGISTRY


class FakeResponse:
    def __init__(self, status_code=201):
        self.status_code = status_code


class FakeRequest:
    def __init__(self, headers=None, method="GET", path="/hello"):
        self.headers = headers
        self.method = method
        self.path = path


def test_resolve_correlation_id_prefers_x_correlation_id():
    request = FakeRequest(headers={"X-Correlation-Id": "cid-1", "X-Request-Id": "req-2"})
    assert pipeline.resolve_correlation_id(request) == "cid-1"


def test_resolve_correlation_id_falls_back_to_x_request_id():
    request = FakeRequest(headers={"x-request-id": "req-2"})
    assert pipeline.resolve_correlation_id(request) == "req-2"


def test_resolve_correlation_id_generates_uuid_when_absent():
    import uuid as uuid_module

    for headers in (None, {}, {"other": "1"}):
        cid = pipeline.resolve_correlation_id(FakeRequest(headers=headers))
        uuid_module.UUID(cid)  # raises if not a valid uuid


def test_middleware_records_success():
    before = REGISTRY.requests_total._values.get(("/hello", "GET", "2xx"), 0.0)
    result = pipeline.middleware(FakeRequest(), lambda req: FakeResponse(200))
    assert result.status_code == 200
    assert REGISTRY.requests_total._values[("/hello", "GET", "2xx")] == before + 1.0


def test_middleware_handles_missing_method_and_path_defaults():
    request = FakeRequest(method=None, path="")
    result = pipeline.middleware(request, lambda req: FakeResponse(404))
    assert result.status_code == 404
    assert REGISTRY.requests_total._values.get(("/", "GET", "4xx")) is not None


def test_middleware_exception_still_records_and_reraises():
    calls_before = REGISTRY.requests_total._values.get(("/hello", "GET", "5xx"), 0.0)

    def boom(request):
        raise RuntimeError("inner view failure escaped to middleware")

    with pytest.raises(RuntimeError):
        pipeline.middleware(FakeRequest(), boom)
    assert REGISTRY.requests_total._values[("/hello", "GET", "5xx")] == calls_before + 1.0
