"""Core API routes: thin HTTP layer over the services package."""

from __future__ import annotations

import platform
import sys

from chalice import Blueprint, Response

from chalicelib.config import get_config
from chalicelib.errors import InvalidRequest, ResourceNotFound
from chalicelib.handlers.views import handle_view_errors
from chalicelib.observability.metrics import REGISTRY
from chalicelib.services import greeter, readiness, validation
from chalicelib.version import __version__

core_routes = Blueprint(__name__)

ENDPOINTS = {
    "index": "/",
    "hello": "/hello?name=<optional>",
    "greet": "/greet/{name}",
    "health": "/health",
    "ready": "/ready",
    "version": "/version",
    "metrics": "/metrics",
    "demo_error": "/demo/error?kind=bad_request|unavailable|boom",
    "demo_slow": "/demo/slow?delay=0.5",
}


def query_param(name: str) -> str | None:
    params = core_routes.current_request.query_params
    return params.get(name) if params else None


@core_routes.route("/", methods=["GET"])
@handle_view_errors
def index() -> dict:
    cfg = get_config()
    return {
        "service": cfg.service_name,
        "stage": cfg.stage,
        "version": __version__,
        "description": "AWS Chalice DevOps Lab API",
        "endpoints": ENDPOINTS,
    }


@core_routes.route("/hello", methods=["GET"])
@handle_view_errors
def hello() -> dict:
    validated = validation.validate_name(query_param("name"))
    payload = greeter.build_greeting(validated)
    payload["stage"] = get_config().stage
    return payload


@core_routes.route("/greet/{name}", methods=["GET"])
@handle_view_errors
def greet(name: str) -> dict:
    if not name or not validation.NAME_PATTERN.match(name):
        raise InvalidRequest("Path parameter 'name' must be 1-64 chars of letters, digits, space, '_' or '-'")
    return greeter.build_greeting(name)


@core_routes.route("/health", methods=["GET"])
@handle_view_errors
def health() -> dict:
    """Liveness: no external dependencies, process is up."""
    cfg = get_config()
    return {"status": "ok", "service": cfg.service_name, "stage": cfg.stage}


@core_routes.route("/ready", methods=["GET"])
@handle_view_errors
def ready() -> Response:
    cfg = get_config()
    ok, payload = readiness.readiness(cfg)
    return Response(
        body=payload,
        status_code=200 if ok else 503,
        headers={"Content-Type": "application/json"},
    )


@core_routes.route("/version", methods=["GET"])
@handle_view_errors
def version() -> dict:
    cfg = get_config()
    return {
        "version": __version__,
        "stage": cfg.stage,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "arch": platform.machine(),
    }


@core_routes.route("/metrics", methods=["GET"])
@handle_view_errors
def metrics() -> Response:
    cfg = get_config()
    if not cfg.metrics_enabled:
        raise ResourceNotFound("Metrics endpoint is disabled")
    return Response(
        body=REGISTRY.render(),
        status_code=200,
        headers={"Content-Type": "text/plain; version=0.0.4"},
    )
