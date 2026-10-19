"""Unit tests: configuration loading and validation."""

from __future__ import annotations

import pytest

from chalicelib.config import Config, get_config, set_config

BASE_KEYS = {
    "APP_STAGE": None,
    "LOG_LEVEL": None,
    "SERVICE_NAME": None,
    "DEMO_ENDPOINTS_ENABLED": None,
    "METRICS_ENABLED": None,
    "METRICS_BACKEND": None,
    "MAINTENANCE_MODE": None,
    "DEMO_MAX_DELAY_SECONDS": None,
    "AWS_LAMBDA_FUNCTION_NAME": None,
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in BASE_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults():
    cfg = Config.load()
    assert cfg.stage == "dev"
    assert cfg.service_name == "chalice-api"
    assert cfg.log_level == "INFO"
    assert cfg.demo_enabled is True
    assert cfg.metrics_enabled is True
    assert cfg.metrics_backend == "inproc"
    assert cfg.on_lambda is False
    assert cfg.maintenance is False
    assert cfg.demo_max_delay == 5.0
    assert cfg.is_prod is False


def test_metrics_backend_explicit(monkeypatch):
    monkeypatch.setenv("METRICS_BACKEND", "cloudwatch")
    assert Config.load().metrics_backend == "cloudwatch"


def test_invalid_metrics_backend_raises(monkeypatch):
    monkeypatch.setenv("METRICS_BACKEND", "statsd")
    with pytest.raises(ValueError, match="METRICS_BACKEND"):
        Config.load()


def test_on_lambda_detected_and_defaults_backend(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chalice-devops-lab-prod")
    cfg = Config.load()
    assert cfg.on_lambda is True
    assert cfg.metrics_backend == "cloudwatch"  # auto-picked when unset on Lambda


def test_on_lambda_backend_can_be_overridden(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "fn")
    monkeypatch.setenv("METRICS_BACKEND", "inproc")
    cfg = Config.load()
    assert cfg.on_lambda is True
    assert cfg.metrics_backend == "inproc"


def test_stage_normalized_and_prod_forces_demo_off(monkeypatch):
    monkeypatch.setenv("APP_STAGE", " PROD ")
    monkeypatch.setenv("DEMO_ENDPOINTS_ENABLED", "true")
    cfg = Config.load()
    assert cfg.stage == "prod"
    assert cfg.is_prod is True
    assert cfg.demo_enabled is False


@pytest.mark.parametrize("stage", ["nope", "", "PROD2"])
def test_invalid_stage_raises(monkeypatch, stage):
    monkeypatch.setenv("APP_STAGE", stage)
    with pytest.raises(ValueError, match="APP_STAGE"):
        Config.load()


def test_invalid_log_level_raises(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Config.load()


def test_valid_log_level_uppercased(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    assert Config.load().log_level == "WARNING"


def test_delay_non_numeric(monkeypatch):
    monkeypatch.setenv("DEMO_MAX_DELAY_SECONDS", "abc")
    with pytest.raises(ValueError, match="must be a number"):
        Config.load()


@pytest.mark.parametrize("value", ["0", "-1", "31"])
def test_delay_out_of_range(monkeypatch, value):
    monkeypatch.setenv("DEMO_MAX_DELAY_SECONDS", value)
    with pytest.raises(ValueError, match="must be in"):
        Config.load()


@pytest.mark.parametrize("raw,expected", [("1", True), ("TRUE", True), ("off", False), ("", False)])
def test_env_bool(monkeypatch, raw, expected):
    monkeypatch.setenv("MAINTENANCE_MODE", raw)
    assert Config.load().maintenance is expected


def test_env_bool_absent_defaults():
    assert Config.load().maintenance is False
    assert Config.load().metrics_enabled is True


def test_get_set_config_roundtrip():
    sentinel = Config(stage="staging")
    set_config(sentinel)
    assert get_config() is sentinel


def test_get_config_lazy_loads_when_cache_empty(monkeypatch):
    from chalicelib import config as config_module

    monkeypatch.setenv("APP_STAGE", "dev")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    original = config_module._RUNTIME.get("cfg")
    config_module._RUNTIME.clear()
    try:
        loaded = get_config()
        assert loaded.stage == "dev"
        assert get_config() is loaded  # second call hits the cache
    finally:
        if original is not None:
            config_module._RUNTIME["cfg"] = original
        else:
            config_module._RUNTIME.clear()
