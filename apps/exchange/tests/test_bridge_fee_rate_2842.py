"""#2842: BRIDGE_FEE_RATE must be a finite fraction in [0, 1] — 'nan',
'inf', '-1' and '5.0' previously flowed into the deposit estimate as a
500 (InvalidOperation) or a >100% fee with negative net."""

import importlib

import pytest


@pytest.fixture
def reload_config(monkeypatch):
    import apps.exchange.simple_exchange.config as cfg

    def _load(env_value):
        monkeypatch.setenv("AITBC_SKIP_ENV_FILES", "1")
        monkeypatch.setenv("BRIDGE_FEE_RATE", env_value)
        return importlib.reload(cfg).bridge_config

    yield _load
    # restore the module-level config computed from the real environment
    monkeypatch.delenv("BRIDGE_FEE_RATE", raising=False)
    importlib.reload(cfg)


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "-0.5", "1.5", "5.0", "abc"])
def test_invalid_fee_rate_falls_back(reload_config, bad):
    cfg = reload_config(bad)
    assert cfg.fee_rate == 0.005


@pytest.mark.parametrize("good,expected", [("0", 0.0), ("0.005", 0.005), ("1", 1.0), ("0.25", 0.25)])
def test_valid_fee_rate_accepted(reload_config, good, expected):
    cfg = reload_config(good)
    assert cfg.fee_rate == expected
