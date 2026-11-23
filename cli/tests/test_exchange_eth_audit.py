"""Exchange ETH-command audit fixes: #2548 wallet endpoint config, #2581
click.Abort recaught by broad except, #2582 deposit-eth premature success,
#2583 --amount documented as AIT."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from aitbc_cli.commands.market import exchange as ex

GOOD_BRIDGE = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"
RECIPIENT = "0x" + "22" * 20


# ------------------------------------------------------------------ #2548


class _FakeClient:
    """Captures constructor args; serves canned GETs."""

    instances: list["_FakeClient"] = []

    def __init__(self, base_url=None, timeout=None, api_key=None, **kw):
        self.base_url = base_url
        self.api_key = api_key
        _FakeClient.instances.append(self)

    def get(self, path, params=None):
        if path == "/v1/exchange/price":
            return {"eth_usd": "1", "ait_usd": "1", "exchange_rate": "1", "timestamp": "t"}
        if path == "/v1/exchange/status":
            return {"enabled": True, "wallet_address": "0xw", "rpc_url": "u", "poll_interval": 1}
        if path == "/v1/exchange/deposits":
            return {"deposits": []}
        return {}


@pytest.fixture
def wallet_config(monkeypatch):
    """A config whose wallet daemon differs from every hard-coded default."""
    cfg = SimpleNamespace(
        wallet_daemon_url="http://wallet.internal:9999",
        wallet_api_key="wk-secret",
        api_key="generic-wrong-key",
    )
    monkeypatch.setattr(ex, "get_config", lambda: cfg)
    monkeypatch.setattr(ex, "AITBCHTTPClient", _FakeClient)
    _FakeClient.instances.clear()
    return cfg


@pytest.mark.parametrize(
    "args",
    [
        ["price"],
        ["list-deposits"],
        ["status"],
    ],
)
def test_exchange_reads_use_wallet_daemon_config(wallet_config, args):
    res = CliRunner().invoke(ex.exchange, args, obj={})
    assert res.exit_code == 0, res.output
    assert _FakeClient.instances, "no wallet client built"
    client = _FakeClient.instances[-1]
    assert client.base_url == "http://wallet.internal:9999"
    assert client.api_key == "wk-secret"


def test_mint_ait_uses_wallet_daemon_config(wallet_config, monkeypatch):
    deposit = {
        "id": "d1",
        "status": "pending",
        "amount_ait": "1",
        "amount_eth": "0.1",
        "from_address": "0xfrom",
        "recipient": RECIPIENT,
    }

    class DepositClient(_FakeClient):
        def get(self, path, params=None):
            if path == "/v1/exchange/deposits/d1":
                return deposit
            return {}

        def post(self, path, json=None):
            return {"success": True}

    monkeypatch.setattr(ex, "AITBCHTTPClient", DepositClient)
    monkeypatch.setattr(ex, "_confirm_mint", lambda d: False)  # stop before any chain work
    res = CliRunner().invoke(ex.mint_ait, ["--deposit-id", "d1"], obj={})
    assert res.exit_code == 0, res.output
    assert DepositClient.instances[-1].base_url == "http://wallet.internal:9999"
    assert DepositClient.instances[-1].api_key == "wk-secret"


# ------------------------------------------------------------------ #2581


def test_withdraw_nonpositive_amount_aborts_without_rewrap():
    res = CliRunner().invoke(ex.withdraw_eth, ["--amount", "0", "--address", RECIPIENT], obj={})
    assert res.exit_code != 0
    assert "Amount and address are required" in res.output
    assert "Error withdrawing ETH" not in res.output


def test_withdraw_inner_abort_not_rewrapped(monkeypatch):
    monkeypatch.setattr(ex, "get_config", lambda: SimpleNamespace())
    monkeypatch.setattr(ex, "_execute_eth_withdrawal", MagicMock(side_effect=click.Abort()))
    res = CliRunner().invoke(ex.withdraw_eth, ["--amount", "0.1", "--address", RECIPIENT], input="y\n", obj={})
    assert res.exit_code != 0
    assert "Error withdrawing ETH" not in res.output


def test_execute_withdrawal_missing_rpc_aborts_clean(monkeypatch, capsys):
    monkeypatch.delenv("ETH_RPC_URL", raising=False)
    monkeypatch.delenv("BRIDGE_PRIVATE_KEY", raising=False)
    with pytest.raises(click.Abort):
        ex._execute_eth_withdrawal(SimpleNamespace(), Decimal("0.1"), RECIPIENT)
    assert "ETH_RPC_URL not configured" in capsys.readouterr().out


def test_deposit_invalid_bridge_address_aborts_without_rewrap(monkeypatch):
    monkeypatch.setattr(ex, "get_config", lambda: SimpleNamespace())
    monkeypatch.setattr(ex, "EthereumRPCClient", lambda: MagicMock())
    monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
    res = CliRunner().invoke(ex.deposit_eth, ["--amount", "0.1", "--bridge-address", "notanaddress"], obj={})
    assert res.exit_code != 0
    assert "Invalid bridge deposit address" in res.output
    assert "Error depositing ETH" not in res.output


# ------------------------------------------------------------------ #2582


def _fake_w3(receipt_status: int):
    tx_hash = SimpleNamespace(hex=lambda: "0x" + "ab" * 32)
    w3 = SimpleNamespace()
    w3.to_wei = lambda amount, unit: 1
    w3.eth = SimpleNamespace(
        gas_price=1,
        get_transaction_count=lambda *a, **k: 0,
        estimate_gas=lambda *a, **k: 21_000,  # #2755: default path estimates gas
        account=SimpleNamespace(sign_transaction=lambda tx, key: SimpleNamespace(raw_transaction=b"\x01")),
        send_raw_transaction=lambda raw: tx_hash,
        wait_for_transaction_receipt=lambda h, timeout=None: SimpleNamespace(status=receipt_status),
    )
    return w3, tx_hash


def _deposit_patches(monkeypatch, w3):
    monkeypatch.setattr(ex, "get_config", lambda: SimpleNamespace())
    monkeypatch.setattr(ex, "EthereumRPCClient", lambda: SimpleNamespace(_get_web3=lambda: w3))
    monkeypatch.setattr(
        ex,
        "load_wallet_for_payment",
        lambda *a, **k: (RECIPIENT, "0x" + "11" * 32, None),
    )


def test_deposit_eth_waits_for_successful_receipt(monkeypatch):
    w3, _ = _fake_w3(receipt_status=1)
    _deposit_patches(monkeypatch, w3)
    res = CliRunner().invoke(
        ex.deposit_eth,
        ["--amount", "0.1", "--bridge-address", GOOD_BRIDGE],
        obj={},
    )
    assert res.exit_code == 0, res.output
    assert "Deposited 0.1 Sepolia ETH" in res.output


def test_deposit_eth_failed_receipt_is_not_success(monkeypatch):
    w3, _ = _fake_w3(receipt_status=0)
    _deposit_patches(monkeypatch, w3)
    res = CliRunner().invoke(
        ex.deposit_eth,
        ["--amount", "0.1", "--bridge-address", GOOD_BRIDGE],
        obj={},
    )
    assert res.exit_code != 0
    assert "failed on-chain" in res.output
    assert "Deposited 0.1 Sepolia ETH" not in res.output


# ------------------------------------------------------------------ #2583


def test_eth_amount_help_says_eth_not_ait():
    for cmd in (ex.deposit_eth, ex.withdraw_eth):
        amount_help = " ".join(str(getattr(p, "help", "") or "") for p in cmd.params if p.name == "amount")
        assert "ETH" in amount_help, cmd.name
        assert "Amount of AIT" not in amount_help, cmd.name
