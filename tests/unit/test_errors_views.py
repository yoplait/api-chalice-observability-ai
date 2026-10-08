"""Unit tests: error model and the centralized view-error decorator."""

from __future__ import annotations

import pytest

from chalicelib.errors import ApiError, InvalidRequest, ResourceNotFound, error_body
from chalicelib.handlers.views import handle_view_errors
from chalicelib.logging import correlation_id_var


def test_api_error_titles_and_defaults():
    assert ApiError("m", status=400).title == "Bad Request"
    assert ApiError("m", status=599).title == "Error"
    assert ApiError("m").status == 500
    assert ApiError("m", status=404, title="Custom").title == "Custom"
    assert InvalidRequest("bad").status == 400
    assert ResourceNotFound().message == "Resource not found"
    assert ResourceNotFound("gone").status == 404


def test_error_body_shape():
    body = error_body(400, "Bad Request", "detail", "cid")
    assert body == {"error": {"code": 400, "title": "Bad Request", "detail": "detail", "correlation_id": "cid"}}


def test_decorator_passes_through_ok():
    @handle_view_errors
    def view(x: int) -> dict:
        return {"x": x}

    assert view(3) == {"x": 3}


def test_decorator_maps_api_error():
    token = correlation_id_var.set("cid-1")

    @handle_view_errors
    def view() -> None:
        raise InvalidRequest("nope")

    response = view()
    assert response.status_code == 400
    assert response.body["error"]["detail"] == "nope"
    assert response.body["error"]["correlation_id"] == "cid-1"
    correlation_id_var.reset(token)


def test_decorator_maps_unexpected_to_500():
    @handle_view_errors
    def view() -> None:
        raise RuntimeError("crash")

    response = view()
    assert response.status_code == 500
    assert response.body["error"]["code"] == "InternalServerError"
    assert response.body["error"]["detail"] == "An unexpected error occurred"


def test_error_envelope_is_consistent_across_classes():
    for err in (InvalidRequest("a"), ResourceNotFound("b"), ApiError("c", status=503)):
        body = error_body(err.title, err.title, err.message, "cid")
        assert set(body["error"]) == {"code", "title", "detail", "correlation_id"}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
