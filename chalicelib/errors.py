"""Centralized error model. Domain exceptions are converted to JSON error
responses by the middleware in chalicelib/observability/pipeline.py, the
supported centralization mechanism in Chalice >= 1.31 (@app.error_handler
and @app.before_request were removed from the framework)."""

from __future__ import annotations

STATUS_TITLES = {
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


class ApiError(Exception):
    """Application error mapped to a JSON error response by the pipeline."""

    def __init__(self, message: str, status: int = 500, title: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.title = title or STATUS_TITLES.get(status, "Error")
        self.message = message


class InvalidRequest(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status=400)


class ResourceNotFound(ApiError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status=404, title="Not Found")


def error_body(code: int, title: str, detail: str, correlation_id: str) -> dict:
    return {"error": {"code": code, "title": title, "detail": detail, "correlation_id": correlation_id}}
