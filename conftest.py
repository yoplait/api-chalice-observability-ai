"""Shared pytest fixtures. Sets a deterministic env before importing the app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_STAGE", "dev")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("METRICS_ENABLED", "true")
os.environ.setdefault("DEMO_ENDPOINTS_ENABLED", "true")

import pytest  # noqa: E402
from chalice.test import Client  # noqa: E402

from chalicelib.config import Config, get_config, set_config  # noqa: E402


@pytest.fixture(scope="session")
def client():
    import app as app_module

    with Client(app_module.app, stage_name="dev", project_dir=str(ROOT)) as c:
        yield c


@pytest.fixture
def restore_config():
    original = get_config()
    yield original
    set_config(original)


@pytest.fixture
def use_config(restore_config):
    def _apply(cfg: Config) -> Config:
        set_config(cfg)
        return cfg

    return _apply
