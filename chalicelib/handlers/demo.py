"""Demo routes: controlled failure and latency simulation for observability
demos. Hard-disabled when APP_STAGE=prod (see chalicelib/config.py), so they
can never fire accidentally in production."""

from __future__ import annotations

import time

from chalice import Blueprint

from chalicelib.config import get_config
from chalicelib.errors import ApiError, InvalidRequest
from chalicelib.handlers.views import handle_view_errors
from chalicelib.services import validation

demo_routes = Blueprint(__name__)

ERROR_KINDS = ("bad_request", "unavailable", "boom")


def _query_param(name: str, default: str | None = None) -> str | None:
    params = demo_routes.current_request.query_params
    value = params.get(name) if params else None
    return value if value is not None else default


def _ensure_demo_enabled() -> None:
    cfg = get_config()
    if not cfg.demo_enabled:
        raise ApiError("Demo endpoints are disabled in this stage", status=404, title="Not Found")


@demo_routes.route("/demo/error", methods=["GET"])
@handle_view_errors
def demo_error() -> dict:
    _ensure_demo_enabled()
    kind = _query_param("kind", "bad_request")
    if kind not in ERROR_KINDS:
        raise InvalidRequest(f"Parameter 'kind' must be one of {list(ERROR_KINDS)}")
    if kind == "bad_request":
        raise InvalidRequest("Simulated client error")
    if kind == "unavailable":
        raise ApiError("Simulated dependency outage", status=503, title="Service Unavailable")
    raise RuntimeError("Simulated unhandled crash")


@demo_routes.route("/demo/exception", methods=["GET"])
@handle_view_errors
def demo_exception() -> dict:
    """Controlled demonstration of the centralized unhandled-exception path."""
    _ensure_demo_enabled()
    raise RuntimeError("Simulated unhandled exception")


@demo_routes.route("/demo/slow", methods=["GET"])
@handle_view_errors
def demo_slow() -> dict:
    _ensure_demo_enabled()
    cfg = get_config()
    seconds = validation.validate_delay(_query_param("delay"), cfg.demo_max_delay)
    time.sleep(seconds)
    return {"slept_seconds": seconds, "status": "done"}
