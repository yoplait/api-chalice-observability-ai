"""Request pipeline middleware: correlation id, timing, structured access
log and in-process metrics.

Registered with @app.middleware("http") in app.py. Centralized error mapping
lives in chalicelib/handlers/views.py because Chalice >= 1.33 converts view
exceptions to generic responses inside the framework (they never reach
middleware). Behavior is identical in `chalice local` and AWS Lambda.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable

from chalicelib.logging import correlation_id_var
from chalicelib.observability.metrics import REGISTRY

log = logging.getLogger("chalicelib.access")


def resolve_correlation_id(request: Any) -> str:
    headers = {k.lower(): v for k, v in (getattr(request, "headers", None) or {}).items()}
    cid = headers.get("x-correlation-id") or headers.get("x-request-id")
    if not cid:
        cid = str(uuid.uuid4())
    return cid


def middleware(request: Any, get_response: Callable[[Any], Any]) -> Any:
    correlation_id_var.set("")
    token = correlation_id_var.set(resolve_correlation_id(request))
    started = time.perf_counter()
    response: Any = None
    try:
        response = get_response(request)
    finally:
        correlation_id_var.reset(token)
        duration = time.perf_counter() - started
        status = int(getattr(response, "status_code", 500))
        route = getattr(request, "path", "") or "/"
        REGISTRY.observe_request(route, (request.method or "GET").upper(), status, duration)
        log.info(
            "request completed",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "route": route,
                    "status": status,
                    "duration_ms": round(duration * 1000, 2),
                }
            },
        )
    return response
