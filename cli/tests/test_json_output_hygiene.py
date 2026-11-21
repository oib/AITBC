"""CLI-MACHINE-OUTPUT-HYGIENE-1 (#2439): JSON output must carry full values.

Covers the five reported cases: untruncated addresses/hashes in JSON,
one AIT money representation in `transactions search`, consistent numeric
types in `exchange add-liquidity`, filled timestamps, and the bridge
status backend hint.
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.transactions as tx_mod
import aitbc_cli.commands.wallet.bridge as bridge_mod
from aitbc_cli.commands.exchange.main import exchange
from aitbc_cli.commands.transactions import transactions
from aitbc_cli.commands.wallet import basic as wallet_basic
from aitbc_cli.commands.wallet.basic import wallet


@pytest.fixture
def runner():
    return CliRunner()


_TX_HASH = "0x" + "ab" * 32
_ADDR = "0x" + "11" * 20


# --- (a) wallet transactions: full values in JSON, truncated in table ---


def _patch_wallet_txn_deps(monkeypatch):
    class _WalletClient:
        def get(self, path):
            return {"items": [{"wallet_id": "w1", "metadata": {"address": _ADDR}}]}

    class _Rpc:
        def __init__(self, *a, **kw):
            pass

        def get_json(self, path, params=None):
            return [
                {
                    "transaction_id": "tx-1",
                    "tx_hash": _TX_HASH,
                    "sender": _ADDR,
                    "recipient": "0x" + "22" * 20,
                    "value": 64,
                    "fee": 10,
                    "status": "confirmed",
                    "created_at": "2026-11-21T10:00:00+00:00",
                }
            ]

    monkeypatch.setattr(wallet_basic, "get_wallet_client", lambda: _WalletClient())
    monkeypatch.setattr(wallet_basic, "AITBCHTTPClient", _Rpc)
    monkeypatch.setattr(
        wallet_basic,
        "get_config",
        lambda: SimpleNamespace(blockchain_rpc_url="http://rpc.test"),
    )
    monkeypatch.setattr(wallet_basic, "to_eip55", lambda a: a)


def test_wallet_transactions_json_has_full_values(runner, monkeypatch):
    _patch_wallet_txn_deps(monkeypatch)
    result = runner.invoke(wallet, ["transactions", "--name", "w1"], obj={"output_format": "json", "wallet_name": "w1"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    tx = payload["transactions"][0]
    assert tx["tx_hash"] == _TX_HASH
    assert tx["sender"] == _ADDR
    assert tx["recipient"] == "0x" + "22" * 20
    assert tx["value"] == "0.00000178 AIT"


def test_wallet_transactions_table_truncates(runner, monkeypatch):
    _patch_wallet_txn_deps(monkeypatch)
    result = runner.invoke(wallet, ["transactions", "--name", "w1"], obj={"output_format": "table", "wallet_name": "w1"})
    assert result.exit_code == 0, result.output
    assert _TX_HASH not in result.output
    # sender/recipient rows truncated; the wallet's own address field stays full
    assert "0x111111111111111111..." in result.output
    assert "0xababababababab..." in result.output


# --- (b)+(d) transactions search: AIT strings, raw units kept, timestamp filled ---


def test_search_row_normalization():
    row = {
        "transaction_id": "tx-1",
        "tx_hash": _TX_HASH,
        "value": 360000000,
        "fee": 360000,
        "timestamp": None,
        "created_at": "2026-11-01T00:00:00+00:00",
    }
    out = tx_mod._normalize_search_row(row)
    assert isinstance(out, dict)
    assert out["value"] == "10 AIT"
    assert out["fee"] == "0.01 AIT"
    assert out["value_units"] == 360000000
    assert out["fee_units"] == 360000
    assert out["timestamp"] == "2026-11-01T00:00:00+00:00"
    # input row untouched
    assert row["value"] == 360000000


def test_search_row_explorer_alias_fields():
    # Explorer rows carry value/amount duplicates plus *_ait fields.
    row = {
        "transaction_id": "tx-2",
        "tx_hash": _TX_HASH,
        "value": 360000000,
        "amount": 360000000,
        "amount_ait": "10 AIT",
        "fee": 360000,
        "fee_ait": "0.01 AIT",
        "created_at": "2026-11-01T00:00:00+00:00",
        "timestamp": None,
    }
    out = tx_mod._normalize_search_row(row)
    assert isinstance(out, dict)
    assert out["value"] == "10 AIT"
    assert out["amount"] == "10 AIT"
    assert out["amount_units"] == 360000000
    assert out["fee"] == "0.01 AIT"


def test_search_via_rpc_emits_normalized_json(runner, monkeypatch):
    class _Rpc:
        def __init__(self, *a, **kw):
            pass

        def get_json(self, path, params=None):
            return [
                {
                    "transaction_id": "tx-9",
                    "tx_hash": _TX_HASH,
                    "sender": _ADDR,
                    "recipient": "0x" + "33" * 20,
                    "value": 1000000,
                    "fee": 500,
                    "status": "confirmed",
                    "timestamp": None,
                    "block_timestamp": "2026-11-20T12:00:00+00:00",
                }
            ]

    monkeypatch.setattr(tx_mod, "AITBCHTTPClient", _Rpc)
    monkeypatch.setattr(tx_mod, "_resolve_transaction_rpc_url", lambda u: "http://rpc.test")
    result = runner.invoke(transactions, ["search", "--address", _ADDR], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert rows[0]["value"] == "0.02777778 AIT"
    assert rows[0]["value_units"] == 1000000
    assert rows[0]["timestamp"] == "2026-11-20T12:00:00+00:00"


# --- (c) exchange add-liquidity: consistent decimal-string types ---


def test_add_liquidity_emits_decimal_strings(runner, monkeypatch, tmp_path):
    exchanges = {"testex": {"trading_pairs": [{"symbol": "AIT/ETH", "base_liquidity": 5000.0, "quote_liquidity": "100.5"}]}}
    aitbc_dir = tmp_path / ".aitbc"
    aitbc_dir.mkdir()
    exchanges_file = aitbc_dir / "exchanges.json"
    exchanges_file.write_text(json.dumps(exchanges))
    # Path.home() reads HOME on POSIX.
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(
        exchange,
        ["add-liquidity", "--pair", "AIT/ETH", "--amount", "10", "--side", "buy"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["amount"] == "10"
    assert isinstance(payload["base_liquidity"], str)
    assert isinstance(payload["quote_liquidity"], str)
    assert payload["quote_liquidity"] == "110.5"
    assert payload["base_liquidity"] == "5000.0"


# --- (e) wallet bridge status/float name the answering backend ---


class _BridgeClient:
    base_url = "http://wallet-daemon.test:8400"

    def __init__(self, doc):
        self._doc = doc

    def get(self, path, params=None):
        return self._doc


def test_bridge_status_window_names_backend(runner, monkeypatch):
    doc = {
        "windows": {
            "last_24h": {
                "timezone": "UTC",
                "since": "2026-11-20T00:00:00+00:00",
                "withdrawals_eth": "0",
                "sell_eth": "0",
                "exchange_eth": "0",
                "total_eth": "0",
            }
        },
        "sell_daily_cap": {},
    }
    monkeypatch.setattr(bridge_mod, "_hub_bridge_client", lambda url: _BridgeClient(doc))
    result = runner.invoke(bridge_mod.status, ["--24h"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["backend"] == "http://wallet-daemon.test:8400"


def test_bridge_float_names_backend(runner, monkeypatch):
    doc = {"float_ait": "1.5", "windows": {}}
    monkeypatch.setattr(bridge_mod, "_hub_bridge_client", lambda url: _BridgeClient(doc))
    result = runner.invoke(bridge_mod.float_cmd, [], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["backend"] == "http://wallet-daemon.test:8400"
