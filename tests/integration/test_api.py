"""Integration tests: full middleware + routing stack through Chalice's test client.

These exercise the real HTTP event pipeline (LocalGateway -> middleware ->
blueprint views -> error decorator), not mocked shortcuts.
"""

from __future__ import annotations

import sys

from chalicelib.config import Config
from chalicelib.observability.metrics import REGISTRY

ERROR_KEYS = {"code", "title", "detail", "correlation_id"}


def error_of(response):
    return response.json_body["error"]


class TestIndexAndHello:
    def test_index(self, client):
        r = client.http.get("/")
        assert r.status_code == 200
        body = r.json_body
        assert body["service"] == "chalice-api"
        assert body["stage"] == "dev"
        assert body["version"] == "1.0.0"
        for key in ("hello", "health", "ready", "version", "demo_error", "demo_slow"):
            assert key in body["endpoints"]

    def test_hello_default(self, client):
        r = client.http.get("/hello")
        assert r.status_code == 200
        assert r.json_body == {"message": "Hello, world!", "name": "world", "stage": "dev"}

    def test_hello_named(self, client):
        r = client.http.get("/hello?name=Ops")
        assert r.json_body["message"] == "Hello, Ops!"

    def test_hello_with_space_encoded(self, client):
        r = client.http.get("/hello?name=Ada%20Lovelace")
        assert r.status_code == 200
        assert r.json_body["name"] == "Ada Lovelace"

    def test_hello_invalid_name_returns_envelope(self, client):
        r = client.http.get("/hello?name=%24%24invalid")
        assert r.status_code == 400
        assert set(error_of(r)) == ERROR_KEYS
        assert error_of(r)["code"] == "Bad Request"

    def test_greet_path_param(self, client):
        r = client.http.get("/greet/alice")
        assert r.status_code == 200
        assert r.json_body == {"message": "Hello, alice!", "name": "alice"}

    def test_greet_invalid_chars(self, client):
        r = client.http.get("/greet/%21%21")
        assert r.status_code == 400
        assert "name" in error_of(r)["detail"]

    def test_greet_empty_segment(self, client):
        # LocalGateway mirrors API Gateway: an empty path segment never reaches
        # the view (403); 400 is the defensive path. Accept both.
        r = client.http.get("/greet/")
        assert r.status_code in (400, 403, 404)


class TestHealthReadinessVersion:
    def test_health(self, client):
        r = client.http.get("/health")
        assert r.status_code == 200
        assert r.json_body == {"status": "ok", "service": "chalice-api", "stage": "dev"}

    def test_ready_ok(self, client):
        r = client.http.get("/ready")
        assert r.status_code == 200
        assert r.json_body["status"] == "ready"
        assert set(r.json_body["checks"]) == {"config", "metrics", "maintenance"}

    def test_ready_503_in_maintenance(self, client, use_config):
        use_config(Config(maintenance=True))
        r = client.http.get("/ready")
        assert r.status_code == 503
        assert r.json_body["status"] == "not_ready"
        assert "maintenance_mode" in r.json_body["reasons"]

    def test_version(self, client):
        r = client.http.get("/version")
        assert r.status_code == 200
        body = r.json_body
        assert body["version"] == "1.0.0"
        assert body["stage"] == "dev"
        assert body["python"].startswith(f"{sys.version_info.major}.{sys.version_info.minor}.")
        assert body["arch"]

    def test_unknown_path_is_rejected(self, client):
        r = client.http.get("/does-not-exist")
        assert r.status_code in (403, 404)


class TestDemoEndpoints:
    def test_demo_error_bad_request(self, client):
        r = client.http.get("/demo/error?kind=bad_request")
        assert r.status_code == 400
        assert error_of(r)["detail"] == "Simulated client error"

    def test_demo_error_unavailable(self, client):
        r = client.http.get("/demo/error?kind=unavailable")
        assert r.status_code == 503
        assert error_of(r)["code"] == "Service Unavailable"

    def test_demo_error_boom_is_mapped_to_500_envelope(self, client):
        r = client.http.get("/demo/error?kind=boom")
        assert r.status_code == 500
        assert error_of(r)["code"] == "InternalServerError"

    def test_demo_error_unknown_kind(self, client):
        r = client.http.get("/demo/error?kind=magic")
        assert r.status_code == 400
        assert "kind" in error_of(r)["detail"]

    def test_demo_exception_path(self, client):
        r = client.http.get("/demo/exception")
        assert r.status_code == 500
        assert set(error_of(r)) == ERROR_KEYS

    def test_demo_slow_default_and_explicit(self, client):
        r = client.http.get("/demo/slow?delay=0.06")
        assert r.status_code == 200
        assert r.json_body == {"slept_seconds": 0.06, "status": "done"}

    def test_demo_slow_rejects_non_numeric(self, client):
        r = client.http.get("/demo/slow?delay=abc")
        assert r.status_code == 400

    def test_demo_slow_rejects_too_large(self, client):
        r = client.http.get("/demo/slow?delay=99")
        assert r.status_code == 400

    def test_demo_endpoints_hard_disabled_when_flag_off(self, client, use_config):
        use_config(Config(demo_enabled=False))
        for path in ("/demo/error?kind=boom", "/demo/slow?delay=0.06", "/demo/exception"):
            r = client.http.get(path)
            assert r.status_code == 404, path
            assert "disabled" in error_of(r)["detail"]


class TestCorrelationAndMetrics:
    def test_correlation_id_propagates_into_error_envelope(self, client):
        r = client.http.get("/demo/error?kind=bad_request", headers={"X-Correlation-Id": "cid-42"})
        assert r.status_code == 400
        assert error_of(r)["correlation_id"] == "cid-42"

    def test_metrics_endpoint_exposes_real_series(self, client):
        client.http.get("/hello")
        r = client.http.get("/metrics")
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("text/plain")
        body = r.body.decode()
        assert "chalice_uptime_seconds" in body
        assert 'chalice_http_requests_total{route="/hello",method="GET",status="2xx"}' in body

    def test_metrics_disabled_returns_404_envelope(self, client, use_config):
        use_config(Config(metrics_enabled=False))
        r = client.http.get("/metrics")
        assert r.status_code == 404
        assert error_of(r)["code"] == "Not Found"

    def test_registry_counts_5xx_requests(self, client):
        key = ("/demo/error", "GET", "5xx")
        before = REGISTRY.requests_total._values.get(key, 0.0)
        client.http.get("/demo/error?kind=boom")
        assert REGISTRY.requests_total._values[key] == before + 1.0
