"""Resolution-order pins for ``_resolve_market_api_key`` (#2311 replay).

The market service's gated mutating routes (``POST /v1/market/jobs``)
reject anything but its own ``API_KEY``/``MARKET_OPERATOR_API_KEY``. The
customer-side CLI had no market key on node0, so resolution fell through
to the generic ``config.api_key`` — a different service's credential —
and every market-job registration 401'd. The service-scoped env file
must outrank the generic key so a provisioned market key is never
shadowed by it.
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aitbc_cli.config import _resolve_market_api_key

_ENV_VARS = ("MARKET_OPERATOR_API_KEY", "MARKET_API_KEY")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    os.environ.pop("AITBC_SKIP_ENV_FILES", None)


def _config(api_key=None):
    return SimpleNamespace(api_key=api_key)


def _market_env(monkeypatch, mapping):
    def fake_parse(path):
        return dict(mapping) if "aitbc-market.env" in str(path) else {}

    monkeypatch.setattr("aitbc_cli.config._parse_env_file", fake_parse)


@pytest.mark.unit
def test_market_env_file_outranks_generic_api_key(monkeypatch):
    """The regression: generic api_key must not shadow a provisioned market key."""
    _market_env(monkeypatch, {"API_KEY": "market-user-key"})
    assert _resolve_market_api_key(_config(api_key="coordinator-key")) == "market-user-key"


@pytest.mark.unit
def test_market_operator_env_outranks_everything(monkeypatch):
    monkeypatch.setenv("MARKET_OPERATOR_API_KEY", "op-key")
    monkeypatch.setenv("MARKET_API_KEY", "user-key")
    _market_env(monkeypatch, {"API_KEY": "file-key", "MARKET_OPERATOR_API_KEY": "file-op"})
    assert _resolve_market_api_key(_config(api_key="generic")) == "op-key"


@pytest.mark.unit
def test_market_api_env_outranks_env_file(monkeypatch):
    monkeypatch.setenv("MARKET_API_KEY", "env-user-key")
    _market_env(monkeypatch, {"API_KEY": "file-key"})
    assert _resolve_market_api_key(_config(api_key="generic")) == "env-user-key"


@pytest.mark.unit
def test_operator_key_in_env_file_beats_user_key(monkeypatch):
    _market_env(monkeypatch, {"API_KEY": "file-user", "MARKET_OPERATOR_API_KEY": "file-op"})
    assert _resolve_market_api_key(_config(api_key="generic")) == "file-op"


@pytest.mark.unit
def test_generic_api_key_is_last_resort(monkeypatch):
    _market_env(monkeypatch, {})
    assert _resolve_market_api_key(_config(api_key="generic")) == "generic"


@pytest.mark.unit
def test_returns_none_when_nothing_configured(monkeypatch):
    _market_env(monkeypatch, {})
    assert _resolve_market_api_key(_config(api_key=None)) is None
