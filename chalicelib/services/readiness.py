"""Readiness semantics: /ready reports whether this instance can accept
traffic right now. It intentionally avoids real external dependencies (the
health contract must not fail because of them) but models a maintenance
switch so operators can prove the monitoring chain end to end."""

from __future__ import annotations

from chalicelib.config import Config

CHECKS = ("config", "metrics", "maintenance")


def readiness(cfg: Config) -> tuple[bool, dict]:
    reasons: list[str] = []
    if cfg.maintenance:
        reasons.append("maintenance_mode")

    if cfg.metrics_backend == "cloudwatch":
        metrics_status = "cloudwatch"
    elif cfg.metrics_enabled:
        metrics_status = "enabled"
    else:
        metrics_status = "disabled"

    # Prod must report metrics somewhere: either the in-process scrape endpoint
    # is enabled, or we push to CloudWatch (the Lambda-definitive backend).
    if cfg.is_prod and metrics_status == "disabled":
        reasons.append("metrics_disabled_in_prod")

    checks = {
        "config": "ok",
        "metrics": metrics_status,
        "maintenance": "on" if cfg.maintenance else "off",
    }
    ready = not reasons
    payload = {
        "status": "ready" if ready else "not_ready",
        "stage": cfg.stage,
        "checks": checks,
    }
    if reasons:
        payload["reasons"] = reasons
    return ready, payload
