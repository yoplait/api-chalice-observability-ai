"""Unit tests: structured JSON logging."""

from __future__ import annotations

import logging

from chalicelib.logging import CorrelationFilter, JsonFormatter, configure_logging, correlation_id_var


def make_record(msg="hello", level=logging.INFO, name="test.logger"):
    return logging.LogRecord(name, level, "path", 1, msg, None, None)


def test_formatter_basic():
    payload = JsonFormatter().format(make_record())
    assert '"level":"INFO"' in payload
    assert '"message":"hello"' in payload
    assert '"ts":"20' in payload


def test_formatter_includes_extra_fields():
    record = make_record()
    record.extra_fields = {"route": "/hello", "status": 200}
    payload = JsonFormatter().format(record)
    assert '"route":"/hello"' in payload
    assert '"status":200' in payload


def test_formatter_correlation_from_record_attr():
    token = correlation_id_var.set("")
    record = make_record()
    record.correlation_id = "cid-from-record"
    payload = JsonFormatter().format(record)
    assert '"correlation_id":"cid-from-record"' in payload
    correlation_id_var.reset(token)


def test_formatter_correlation_from_contextvar():
    token = correlation_id_var.set("cid-from-var")
    payload = JsonFormatter().format(make_record())
    assert '"correlation_id":"cid-from-var"' in payload
    correlation_id_var.reset(token)


def test_formatter_no_correlation_key_when_empty():
    token = correlation_id_var.set("")
    payload = JsonFormatter().format(make_record())
    assert "correlation_id" not in payload
    correlation_id_var.reset(token)


def test_formatter_exception():
    record = make_record("boom")
    try:
        raise ValueError("kaboom")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    payload = JsonFormatter().format(record)
    assert '"type":"ValueError"' in payload
    assert '"message":"kaboom"' in payload


def test_formatter_default_serialization_for_odd_values():
    record = make_record()
    record.extra_fields = {"weird": {1, 2}}
    payload = JsonFormatter().format(record)
    assert '"weird":' in payload


def test_correlation_filter_sets_attr():
    token = correlation_id_var.set("cid-filter")
    record = make_record()
    assert CorrelationFilter().filter(record) is True
    assert record.correlation_id == "cid-filter"
    correlation_id_var.reset(token)


def test_configure_logging_installs_single_json_handler():
    logger = configure_logging("DEBUG")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    assert root.level == logging.DEBUG
    assert logging.getLogger("chalice.app").level == logging.WARNING
    assert logger.name == "chalicelib"
    # second call must prune the previously installed handler
    configure_logging("INFO")
    assert len(root.handlers) == 1
    assert root.level == logging.INFO
