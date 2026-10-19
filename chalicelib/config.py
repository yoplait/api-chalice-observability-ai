"""Configuration loaded from environment variables. No secrets here: only
non-sensitive settings. Credentials must never be added to this module."""

from __future__ import annotations

import os
from dataclasses import dataclass

VALID_STAGES = ("dev", "staging", "prod")
TRUE_VALUES = ("1", "true", "yes", "on")
VALID_METRICS_BACKENDS = ("inproc", "cloudwatch")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


@dataclass(frozen=True)
class Config:
    stage: str = "dev"
    service_name: str = "chalice-api"
    log_level: str = "INFO"
    demo_enabled: bool = True
    metrics_enabled: bool = True
    metrics_backend: str = "inproc"
    on_lambda: bool = False
    maintenance: bool = False
    demo_max_delay: float = 5.0

    @property
    def is_prod(self) -> bool:
        return self.stage == "prod"

    @classmethod
    def load(cls) -> Config:
        stage = os.environ.get("APP_STAGE", "dev").strip().lower()
        if stage not in VALID_STAGES:
            raise ValueError(f"APP_STAGE must be one of {VALID_STAGES}, got {stage!r}")

        log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError(f"LOG_LEVEL must be DEBUG/INFO/WARNING/ERROR, got {log_level!r}")

        try:
            demo_max_delay = float(os.environ.get("DEMO_MAX_DELAY_SECONDS", "5"))
        except ValueError as exc:
            raise ValueError("DEMO_MAX_DELAY_SECONDS must be a number") from exc
        if not 0.0 < demo_max_delay <= 30.0:
            raise ValueError("DEMO_MAX_DELAY_SECONDS must be in (0, 30]")

        demo_enabled = _env_bool("DEMO_ENDPOINTS_ENABLED", True)
        # Defense in depth: demo endpoints can never be active in prod,
        # even if the flag is mistakenly set to true.
        if stage == "prod":
            demo_enabled = False

        on_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
        default_backend = "cloudwatch" if on_lambda else "inproc"
        metrics_backend_raw = os.environ.get(
            "METRICS_BACKEND", default_backend
        ).strip().lower()
        if metrics_backend_raw not in VALID_METRICS_BACKENDS:
            raise ValueError(
                f"METRICS_BACKEND must be one of {VALID_METRICS_BACKENDS}, "
                f"got {metrics_backend_raw!r}"
            )

        return cls(
            stage=stage,
            service_name=os.environ.get("SERVICE_NAME", "chalice-api"),
            log_level=log_level,
            demo_enabled=demo_enabled,
            metrics_enabled=_env_bool("METRICS_ENABLED", True),
            metrics_backend=metrics_backend_raw,
            on_lambda=on_lambda,
            maintenance=_env_bool("MAINTENANCE_MODE", False),
            demo_max_delay=demo_max_delay,
        )


_RUNTIME: dict[str, Config] = {}


def get_config() -> Config:
    if "cfg" not in _RUNTIME:
        _RUNTIME["cfg"] = Config.load()
    return _RUNTIME["cfg"]


def set_config(cfg: Config) -> None:
    _RUNTIME["cfg"] = cfg
