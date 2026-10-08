"""Centralized error handling for Chalice 1.33.

Chalice >= 1.31 removed @app.error_handler; from 1.33 on, view exceptions
(ChaliceViewError and anything else) are converted to generic JSON *inside*
the framework and never reach middleware. The supported way to centralize
error mapping is a view decorator that converts domain errors to Response
objects. All error payloads therefore share one JSON envelope:

    {"error": {"code", "title", "detail", "correlation_id"}}
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from chalice import Response

from chalicelib.errors import ApiError, error_body
from chalicelib.logging import correlation_id_var

log = logging.getLogger("chalicelib.errors")


def _error_response(status: int, code: str, title: str, detail: str) -> Response:
    return Response(
        body=error_body(code, title, detail, correlation_id_var.get()),
        status_code=status,
        headers={"Content-Type": "application/json"},
    )


def handle_view_errors(view_func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return view_func(*args, **kwargs)
        except ApiError as err:
            log.warning(
                "api error",
                extra={"extra_fields": {"status": err.status, "detail": err.message}},
            )
            return _error_response(err.status, err.title, err.title, err.message)
        except Exception:
            log.exception("unhandled error in view")
            return _error_response(
                500, "InternalServerError", "Internal Server Error", "An unexpected error occurred"
            )

    return wrapper
