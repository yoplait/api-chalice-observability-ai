"""Contract tests: response shape is part of the API promise.

Asserts the documented JSON structure, content types and status codes for
every public endpoint. Run locally via chalice.test and also against a live
server when CHALICE_BASE_URL is set (make smoke-test path).
"""

from __future__ import annotations

import os

import pytest

ERROR_KEYS = {"code", "title", "detail", "correlation_id"}
ENDPOINT_CONTRACTS = {
    "/": {"service": str, "stage": str, "version": str, "description": str, "endpoints": dict},
    "/health": {"status": str, "service": str, "stage": str},
    "/version": {"version": str, "stage": str, "python": str, "arch": str},
    "/ready": {"status": str, "stage": str, "checks": dict},
    "/hello": {"message": str, "name": str, "stage": str},
}


def assert_json_contract(response, expected_keys: dict) -> None:
    body = response.json_body
    assert isinstance(body, dict), "response must be a JSON object"
    assert set(body) == set(expected_keys)
    for key, typ in expected_keys.items():
        assert isinstance(body[key], typ), f"{key} should be {typ}"


@pytest.mark.parametrize("path", sorted(ENDPOINT_CONTRACTS))
def test_success_contracts(client, path):
    response = client.http.get(path)
    assert response.status_code == 200
    assert_json_contract(response, ENDPOINT_CONTRACTS[path])


def test_hello_error_contract(client):
    response = client.http.get("/hello?name=%2A%2A")
    assert response.status_code == 400
    assert set(response.json_body["error"]) == ERROR_KEYS


def test_metrics_content_type_contract(client):
    response = client.http.get("/metrics")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/plain")


@pytest.mark.skipif(not os.environ.get("CHALICE_BASE_URL"), reason="live server not provided")
def test_contract_against_live_server():
    import requests

    base = os.environ["CHALICE_BASE_URL"].rstrip("/")
    for path, contract in ENDPOINT_CONTRACTS.items():
        response = requests.get(f"{base}{path}", timeout=5)
        assert response.status_code == 200, path
        body = response.json()
        assert set(body) == set(contract), path
