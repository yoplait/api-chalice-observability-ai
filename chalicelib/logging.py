"""Structured JSON logging with correlation/request id support."""

from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class JsonFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.")
            + f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        cid = getattr(record, "correlation_id", "") or correlation_id_var.get()
        if cid:
            payload["correlation_id"] = cid
        if record.exc_info:
            exc = record.exc_info[1]
            payload["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        return json.dumps(payload, default=str, separators=(",", ":"))


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> logging.Logger:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationFilter())
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("chalice.app").setLevel("WARNING")
    return logging.getLogger("chalicelib")
