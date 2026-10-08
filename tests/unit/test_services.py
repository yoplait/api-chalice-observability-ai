"""Unit tests: input validation, greeter and readiness services."""

from __future__ import annotations

import pytest

from chalicelib.config import Config
from chalicelib.errors import InvalidRequest
from chalicelib.services import greeter, readiness, validation


@pytest.mark.parametrize("raw", [None, ""])
def test_validate_name_defaults_to_world(raw):
    assert validation.validate_name(raw) == "world"


def test_validate_name_accepts_normal_names():
    assert validation.validate_name("Ops Team_1") == "Ops Team_1"
    assert validation.validate_name("a" * 64) == "a" * 64


@pytest.mark.parametrize("raw", ["$bad", "a" * 65, "name/x", "ünïcode"])
def test_validate_name_rejects_invalid(raw):
    with pytest.raises(InvalidRequest, match="Parameter 'name'"):
        validation.validate_name(raw)


def test_validate_delay_default():
    assert validation.validate_delay(None, 5) == 0.2
    assert validation.validate_delay("", 5) == 0.2


def test_validate_delay_valid_bounds():
    assert validation.validate_delay("0.05", 5) == 0.05
    assert validation.validate_delay("5", 5) == 5.0


def test_validate_delay_non_numeric():
    with pytest.raises(InvalidRequest, match="must be a number"):
        validation.validate_delay("abc", 5)


@pytest.mark.parametrize("raw", ["0.01", "6.0", "-1"])
def test_validate_delay_out_of_range(raw):
    with pytest.raises(InvalidRequest, match="must be between"):
        validation.validate_delay(raw, 5)


def test_validate_delay_ceiling_is_capped_at_30():
    assert validation.validate_delay("25", 60) == 25.0
    with pytest.raises(InvalidRequest, match="30"):
        validation.validate_delay("35", 60)


def test_greeter():
    assert greeter.build_greeting("world") == {"message": "Hello, world!", "name": "world"}


def test_readiness_default_ready():
    cfg = Config(stage="dev")
    ok, payload = readiness.readiness(cfg)
    assert ok is True
    assert payload["status"] == "ready"
    assert payload["checks"] == {"config": "ok", "metrics": "enabled", "maintenance": "off"}
    assert "reasons" not in payload
    assert readiness.CHECKS == ("config", "metrics", "maintenance")


def test_readiness_maintenance_mode():
    cfg = Config(stage="dev", maintenance=True)
    ok, payload = readiness.readiness(cfg)
    assert ok is False
    assert payload["status"] == "not_ready"
    assert "maintenance_mode" in payload["reasons"]
    assert payload["checks"]["maintenance"] == "on"


def test_readiness_metrics_disabled_is_fine_outside_prod():
    cfg = Config(stage="dev", metrics_enabled=False)
    ok, payload = readiness.readiness(cfg)
    assert ok is True
    assert payload["checks"]["metrics"] == "disabled"


def test_readiness_metrics_disabled_in_prod_not_ready():
    cfg = Config(stage="prod", metrics_enabled=False)
    ok, payload = readiness.readiness(cfg)
    assert ok is False
    assert "metrics_disabled_in_prod" in payload["reasons"]
