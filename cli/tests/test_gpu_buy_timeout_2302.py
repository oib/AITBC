"""#2302: the purchase POST must outlast the coordinator's escrow seal wait."""

import inspect

import pytest

import aitbc_cli.commands.market.gpu as gpu_mod


def test_default_exceeds_seal_wait_ceiling(monkeypatch):
    monkeypatch.delenv("AITBC_GPU_BUY_TIMEOUT_SECONDS", raising=False)
    assert gpu_mod._purchase_timeout() >= 180 + 30


@pytest.mark.parametrize("raw,expected", [("300", 300.0), ("0", 240.0), ("-5", 240.0), ("abc", 240.0), ("", 240.0)])
def test_env_override_and_bad_values(monkeypatch, raw, expected):
    monkeypatch.setenv("AITBC_GPU_BUY_TIMEOUT_SECONDS", raw)
    assert gpu_mod._purchase_timeout() == expected


@pytest.mark.parametrize("fn", ["_buy_native", "_notify_evm_purchase"])
def test_purchase_clients_use_the_long_timeout(fn):
    src = inspect.getsource(getattr(gpu_mod, fn)) if hasattr(gpu_mod, fn) else ""
    assert src, f"{fn} missing"
    assert "_purchase_timeout()" in src
