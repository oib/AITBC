"""Tests for #2758 — `exchange prepay deposit` gas handling.

Pins the #2754/#2755 contract: eth_estimateGas + 25% headroom by default,
fail-loud refusal on --send when no usable estimate exists (the old silent
FALLBACK_GAS_LIMIT=100_000 path is gone), and an explicit --gas override
that bypasses estimation entirely.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault(
    "API_KEY_STORAGE_PATH",
    os.path.join(tempfile.mkdtemp(prefix="aitbc-apikeys-"), "api_keys.json"),
)
os.environ.setdefault("COORDINATOR_API_KEY", "test-coordinator-key")
if os.getenv("DEBUG", "").strip().lower() not in ("", "1", "0", "true", "false", "yes", "no", "on", "off"):
    os.environ["DEBUG"] = "false"

import pytest
from click.testing import CliRunner
from eth_account import Account

from aitbc_cli.commands.exchange import prepay as prepay_mod
from aitbc_cli.commands.exchange.prepay import _estimate_gas_limit, deposit

REPO_ROOT = Path(__file__).resolve().parents[2]
WALLET_SRC = REPO_ROOT / "apps" / "wallet" / "src"
SDK_SRC = REPO_ROOT / "packages" / "py" / "aitbc-sdk" / "src"
for src in (SDK_SRC, WALLET_SRC):
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

BUYER = Account.create()
BRIDGE_DEPOSIT = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"


class FakeExchange:
    def __init__(self, *_a, **_kw):
        pass

    def get(self, path):
        if path == "/v1/bridge/status":
            return {"deposit_address": BRIDGE_DEPOSIT}
        if path == "/api/exchange/nodes":
            return {
                "nodes": [
                    {
                        "address": prepay_mod._short(BUYER.address),
                        "status": "registered",
                        "eth_address": prepay_mod._short(BUYER.address),
                    }
                ]
            }
        raise AssertionError(f"unexpected GET {path}")


def _fake_rpc(result_by_method):
    def _call(_ctx, _url, method, params):
        value = result_by_method.get(method)
        return value(method, params) if callable(value) else value

    return _call


BASE_RPC = {
    "eth_chainId": hex(11155111),
    "eth_getTransactionCount": hex(7),
    "eth_gasPrice": hex(2_000_000_000),
    "eth_estimateGas": hex(50_000),
    "eth_getBalance": hex(10**18),
}


@pytest.fixture()
def ctx_fakes(monkeypatch):
    monkeypatch.setattr(
        prepay_mod,
        "_fund_wallet_address",
        lambda ctx, wallet: (BUYER.address, "test-wallet", Path("/tmp/test-wallet.json")),
    )
    monkeypatch.setattr("aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient", FakeExchange)


@pytest.fixture()
def rpc_fn(monkeypatch):
    def apply(table):
        fake = _fake_rpc(table)
        monkeypatch.setattr(prepay_mod, "_rpc_try", fake)
        monkeypatch.setattr(prepay_mod, "_rpc_call", fake)

    return apply


def _invoke(*extra, send=False, password="x"):
    args = [
        "--amount-eth",
        "0.0002",
        "--wallet",
        "test",
        "--exchange-url",
        "http://exchange.test",
        "--eth-rpc-url",
        "http://rpc.test",
    ]
    if send:
        args += ["--send", "--password", password]
    args += list(extra)
    return CliRunner().invoke(deposit, args, obj={"output_format": "json"})


class TestEstimateGasLimit:
    def test_estimate_gets_25pct_headroom(self, monkeypatch):
        monkeypatch.setattr(prepay_mod, "_rpc_try", lambda *a, **k: hex(50_000))
        assert _estimate_gas_limit(None, "http://rpc", "0xabc", "0xdef", 1, "0x") == 62_500

    def test_fractional_estimate_rounds_up(self, monkeypatch):
        monkeypatch.setattr(prepay_mod, "_rpc_try", lambda *a, **k: hex(51_001))
        assert _estimate_gas_limit(None, "http://rpc", "0xabc", "0xdef", 1, "0x") == 63_752

    @pytest.mark.parametrize("bad", [None, "", "not-hex", "0x0", "0x", {"error": "revert"}, Exception("down")])
    def test_unusable_estimate_returns_none(self, monkeypatch, bad):
        monkeypatch.setattr(prepay_mod, "_rpc_try", lambda *a, **k: bad)
        assert _estimate_gas_limit(None, "http://rpc", "0xabc", "0xdef", 1, "0x") is None

    def test_estimate_request_shape(self, monkeypatch):
        seen = {}

        def fake(_ctx, _url, method, params):
            seen[method] = params
            return hex(50_000)

        monkeypatch.setattr(prepay_mod, "_rpc_try", fake)
        _estimate_gas_limit(None, "http://rpc", "0xfrom", "0xto", 1234, "0xdata")
        tx = seen["eth_estimateGas"][0]
        assert tx == {"from": "0xfrom", "to": "0xto", "value": hex(1234), "data": "0xdata"}


class TestPrintGas:
    def test_print_shows_estimated_gas_with_headroom(self, ctx_fakes, rpc_fn):
        rpc_fn(BASE_RPC)
        result = _invoke()
        assert result.exit_code == 0, result.output
        assert '"gas_limit": 62500' in result.output

    def test_print_without_rpc_shows_null_gas_not_a_fallback(self, ctx_fakes, rpc_fn):
        rpc_fn({m: Exception("down") for m in BASE_RPC})
        result = _invoke()
        assert result.exit_code == 0, result.output
        assert '"gas_limit": null' in result.output

    def test_explicit_gas_bypasses_estimation(self, ctx_fakes, rpc_fn, monkeypatch):
        rpc_fn(BASE_RPC)
        monkeypatch.setattr(
            prepay_mod,
            "_estimate_gas_limit",
            lambda *a, **k: pytest.fail("estimation ran despite --gas"),
        )
        result = _invoke("--gas", "21000")
        assert result.exit_code == 0, result.output
        assert '"gas_limit": 21000' in result.output


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"jsonrpc": "2.0", "result": "0x" + "ab" * 32, "id": 1}


class _AsyncClientCtx:
    def __init__(self, sink):
        self._sink = sink

    async def __aenter__(self):
        return self._sink

    async def __aexit__(self, *exc):
        return False


class FakeRawBroadcast:
    def __init__(self):
        self.calls = []

    async def post(self, _url, json=None, **_kw):
        assert json["method"] == "eth_sendRawTransaction"
        self.calls.append(json["params"][0])
        return _Resp()


@pytest.fixture()
def send_fakes(ctx_fakes, rpc_fn, monkeypatch):
    """Everything --send needs: password, wallet key, broadcast sink."""
    monkeypatch.setattr(prepay_mod, "resolve_wallet_password", lambda *a, **k: "test-password")
    monkeypatch.setattr(
        "aitbc_cli.commands.wallet._load_wallet",
        lambda *a, **k: {"address": BUYER.address, "private_key": BUYER.key.hex()},
    )
    sink = FakeRawBroadcast()
    import httpx as real_httpx

    monkeypatch.setattr(real_httpx, "AsyncClient", lambda *a, **k: _AsyncClientCtx(sink))
    return sink


class TestSendGas:
    def test_send_refuses_when_estimate_missing(self, ctx_fakes, rpc_fn, send_fakes):
        rpc_fn({**BASE_RPC, "eth_estimateGas": None})
        result = _invoke(send=True)
        assert result.exit_code != 0
        assert "estimateGas" in result.output
        assert send_fakes.calls == []

    def test_send_refuses_on_jsonrpc_error_object(self, ctx_fakes, rpc_fn, send_fakes):
        rpc_fn({**BASE_RPC, "eth_estimateGas": {"error": {"message": "execution reverted"}}})
        result = _invoke(send=True)
        assert result.exit_code != 0
        assert "estimateGas" in result.output
        assert send_fakes.calls == []

    def test_send_with_explicit_gas_needs_no_estimate(self, ctx_fakes, rpc_fn, send_fakes, monkeypatch):
        rpc_fn({**BASE_RPC, "eth_estimateGas": None})
        monkeypatch.setattr(
            prepay_mod,
            "_estimate_gas_limit",
            lambda *a, **k: pytest.fail("estimation ran despite --gas"),
        )
        result = _invoke("--gas", "21000", send=True)
        assert result.exit_code == 0, result.output
        assert len(send_fakes.calls) == 1
