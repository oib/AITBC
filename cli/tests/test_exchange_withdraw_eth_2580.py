"""#2580: ``market exchange withdraw-eth`` must print the tx hash right after
the broadcast and treat a receipt timeout as submitted-unconfirmed (pending
record + distinct exit + --tx-hash re-check), never a plain failure that
invites a double payout."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from click.testing import CliRunner

from aitbc_cli.commands.market import market

TX_HASH = "0x" + "ab" * 32
TO_ADDR = "0xRecipient0000000000000000000000000001"


class _TxHash:
    """Stand-in for web3's HexBytes — only ``.hex()`` is consumed."""

    def __init__(self, value: str):
        self._value = value

    def hex(self):  # noqa: A003 - mirror HexBytes.hex()
        return self._value


class _FakeAccount:
    address = "0xBridge00000000000000000000000000000001"

    @staticmethod
    def from_key(key):
        return _FakeAccount()

    def sign_transaction(self, tx, key):
        return SimpleNamespace(raw_transaction=b"\x01\x02")


class _FakeEth:
    account = _FakeAccount()
    gas_price = 1

    def __init__(self, *, receipt=None, receipt_exc=None, tx=None):
        self._receipt = receipt
        self._receipt_exc = receipt_exc
        self._tx = tx
        self.sent = []
        self.waits = 0

    def get_transaction_count(self, address):
        return 0

    def send_raw_transaction(self, raw):
        self.sent.append(raw)
        return _TxHash(TX_HASH)

    def wait_for_transaction_receipt(self, tx_hash, timeout):
        self.waits += 1
        if self._receipt_exc is not None:
            raise self._receipt_exc
        return self._receipt

    def get_transaction_receipt(self, tx_hash):
        if self._receipt_exc is not None:
            raise self._receipt_exc
        return self._receipt

    def get_transaction(self, tx_hash):
        return self._tx


class _FakeW3:
    eth_impl = None

    def __init__(self, provider):
        self.eth = _FakeW3.eth_impl if _FakeW3.eth_impl is not None else _FakeEth()

    HTTPProvider = staticmethod(lambda url: url)

    def is_connected(self):
        return True

    def to_wei(self, amount, unit):
        return int(amount) * 10**18

    def from_wei(self, value, unit):
        from decimal import Decimal

        return Decimal(value) / Decimal(10**18)


def _config():
    config = MagicMock()
    config.eth_rpc_url = "http://localhost:8545"
    config.bridge_private_key = "0xkey"
    config.exchange_url = "http://localhost:8106"
    config.api_key = "k"
    return config


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def posted():
    calls = []

    def _post(url, **kwargs):
        calls.append((url, kwargs.get("json")))
        return SimpleNamespace(status_code=200)

    return calls, _post


def _invoke(runner, args, w3_eth, posted, monkeypatch):
    import web3

    _FakeW3.eth_impl = w3_eth
    monkeypatch.setattr(web3, "Web3", _FakeW3)
    monkeypatch.setattr(_FakeW3, "eth_impl", w3_eth)
    _, post = posted
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("aitbc_cli.commands.market.exchange.get_config", lambda: _config())
    try:
        return runner.invoke(market, ["exchange", "withdraw-eth", *args], input="y\n", obj={})
    finally:
        _FakeW3.eth_impl = None


def test_receipt_timeout_reports_unconfirmed_and_records_pending(runner, posted, monkeypatch):
    eth = _FakeEth(receipt_exc=RuntimeError("Transaction is not in the chain after 120 seconds"))
    calls, _ = posted
    result = _invoke(runner, ["--amount", "0.1", "--address", TO_ADDR], eth, posted, monkeypatch)
    assert result.exit_code == 2, result.output
    out = result.output
    assert f"Transaction broadcast: {TX_HASH}" in out
    assert "submitted but not yet confirmed" in out
    assert f"--tx-hash {TX_HASH}" in out
    assert "Withdrew" not in out
    assert len(eth.sent) == 1  # exactly one broadcast — no silent retry
    assert calls and calls[0][1]["status"] == "pending"
    assert calls[0][1]["tx_hash"] == TX_HASH


def test_confirmed_withdrawal_records_completed(runner, posted, monkeypatch):
    eth = _FakeEth(receipt=SimpleNamespace(status=1))
    calls, _ = posted
    result = _invoke(runner, ["--amount", "0.1", "--address", TO_ADDR], eth, posted, monkeypatch)
    assert result.exit_code == 0, result.output
    assert "Withdrew 0.1 ETH" in result.output
    assert calls and calls[0][1]["status"] == "completed"


def test_reverted_receipt_is_a_failure(runner, posted, monkeypatch):
    eth = _FakeEth(receipt=SimpleNamespace(status=0))
    result = _invoke(runner, ["--amount", "0.1", "--address", TO_ADDR], eth, posted, monkeypatch)
    assert result.exit_code != 0
    assert "Transaction failed" in result.output


def test_recheck_pending_exits_2(runner, posted, monkeypatch):
    eth = _FakeEth(receipt=None)
    result = _invoke(runner, ["--tx-hash", TX_HASH], eth, posted, monkeypatch)
    assert result.exit_code == 2, result.output
    assert "still unconfirmed" in result.output


def test_recheck_confirmed_records_completed(runner, posted, monkeypatch):
    eth = _FakeEth(
        receipt=SimpleNamespace(status=1),
        tx={"to": TO_ADDR, "value": 10**17},
    )
    calls, _ = posted
    result = _invoke(runner, ["--tx-hash", TX_HASH], eth, posted, monkeypatch)
    assert result.exit_code == 0, result.output
    assert "confirmed" in result.output
    assert calls and calls[0][1]["status"] == "completed"
    assert calls[0][1]["to_address"] == TO_ADDR


def test_broadcast_failure_is_plain_error(runner, posted, monkeypatch):
    class _BoomEth(_FakeEth):
        def send_raw_transaction(self, raw):
            raise RuntimeError("replacement transaction underpriced")

    eth = _BoomEth()
    calls, _ = posted
    result = _invoke(runner, ["--amount", "0.1", "--address", TO_ADDR], eth, posted, monkeypatch)
    assert result.exit_code != 0 and result.exit_code != 2
    assert "Error withdrawing ETH" in result.output
    assert not calls
