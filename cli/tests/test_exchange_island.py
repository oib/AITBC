"""
Unit tests for Exchange Island CLI commands
"""

import json
import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def mock_credentials_file(tmp_path):
    """Create a temporary credentials file for testing"""
    credentials = {
        "island_id": "test-island-id-12345",
        "island_name": "test-island",
        "island_chain_id": "ait-test",
        "credentials": {
            "genesis_block_hash": "0x1234567890abcdef",
            "genesis_address": "0xabcdef1234567890",
            "rpc_endpoint": "http://localhost:8202",
            "p2p_port": 8001,
        },
        "members": [],
        "joined_at": "2024-01-01T00:00:00",
    }

    # Monkey patch the credentials path
    import aitbc_cli.utils.island_credentials as ic_module

    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(tmp_path / "island_credentials.json")

    # Write credentials to temp file (mode 0600 — loader rejects looser modes)
    with open(ic_module.CREDENTIALS_PATH, "w") as f:
        json.dump(credentials, f)
    os.chmod(ic_module.CREDENTIALS_PATH, 0o600)

    yield credentials

    # Cleanup
    if os.path.exists(ic_module.CREDENTIALS_PATH):
        os.remove(ic_module.CREDENTIALS_PATH)
    ic_module.CREDENTIALS_PATH = original_path


@pytest.fixture
def mock_keystore(tmp_path):
    """Create a temporary keystore for testing.

    Patches the module-level KEYSTORE_PATH constant so commands read
    from a temp file instead of /var/lib/aitbc/keystore/validator_keys.json.
    """
    keystore = {
        "test_key_id": {"public_key_pem": "-----BEGIN PUBLIC KEY-----\ntest_public_key_data\n-----END PUBLIC KEY-----"}
    }

    keystore_path = tmp_path / "validator_keys.json"
    with open(keystore_path, "w") as f:
        json.dump(keystore, f)

    keystore_str = str(keystore_path)

    with patch("aitbc_cli.commands.exchange_island.KEYSTORE_PATH", keystore_str):
        yield keystore_str


@pytest.fixture
def runner():
    """Create a Click CLI runner.

    Tests should use run_with_obj() to invoke commands with a default
    context object so ctx.obj.get("output_format") works.
    """
    return CliRunner()


def test_exchange_buy_command_invalid_amount(mock_credentials_file, runner):
    """Test exchange buy command with invalid amount"""
    from aitbc_cli.commands.exchange_island import exchange_island

    # Use "--" to separate options from positional args so "-10" is not parsed as a flag
    result = runner.invoke(exchange_island, ["buy", "--ait-amount=-10", "--quote-currency", "ETH"], obj={})

    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


def test_exchange_sell_command_invalid_amount(mock_credentials_file, runner):
    """Test exchange sell command with invalid amount"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["sell", "--ait-amount=-10", "--quote-currency", "ETH"], obj={})

    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


def test_exchange_orderbook_invalid_pair(mock_credentials_file, runner):
    """Test exchange orderbook command with invalid pair"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["orderbook", "--pair", "INVALID/PAIR"], obj={})

    assert result.exit_code != 0


def test_exchange_buy_invalid_currency(mock_credentials_file, runner):
    """Test exchange buy command with invalid currency"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["buy", "--ait-amount", "100", "--quote-currency", "INVALID"], obj={})

    assert result.exit_code != 0


def test_exchange_sell_invalid_currency(mock_credentials_file, runner):
    """Test exchange sell command with invalid currency"""
    from aitbc_cli.commands.exchange_island import exchange_island

    result = runner.invoke(exchange_island, ["sell", "--ait-amount", "100", "--quote-currency", "INVALID"], obj={})

    assert result.exit_code != 0


# --- #2204 regression tests: simulated markers, fixed-decimal prices,
# --- hollow-credentials rejection ---


def _live_book_rows():
    """Live-like EXCHANGE rows with sub-1e-4 float prices (the hub case)."""
    return [
        {
            "side": "buy",
            "max_price": 1.26e-05,
            "amount": 500.0,
            "order_id": "b1",
            "pair": "AIT/ETH",
            "status": "open",
            "user_id": "0xu",
            "created_at": "2026-01-01T00:00:00",
        },
        {
            "side": "sell",
            "min_price": 1.3e-05,
            "amount": 300.0,
            "order_id": "s1",
            "pair": "AIT/ETH",
            "status": "open",
            "user_id": "0xu",
            "created_at": "2026-01-01T00:00:00",
        },
    ]


class _FakeHTTPClient:
    """AITBCHTTPClient stand-in returning canned /transactions rows."""

    rows = _live_book_rows()

    def __init__(self, *args, **kwargs):
        pass

    def get_json(self, *args, **kwargs):
        return list(_FakeHTTPClient.rows)


class _DeadHTTPClient:
    """AITBCHTTPClient stand-in that always fails like an unreachable RPC."""

    def __init__(self, *args, **kwargs):
        pass

    def get_json(self, *args, **kwargs):
        from aitbc_cli.utils.http_client import NetworkError

        raise NetworkError("connection refused")


def test_exchange_rates_marks_simulated_on_network_error(mock_credentials_file, runner):
    """rates must label simulated fallback — silent fake data was #2204."""
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _DeadHTTPClient):
        result = runner.invoke(exchange_island, ["rates"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "SIMULATED" in result.output
    assert "(Simulated)" in result.output


def test_exchange_orderbook_marks_simulated_on_network_error(mock_credentials_file, runner):
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _DeadHTTPClient):
        result = runner.invoke(exchange_island, ["orderbook", "--pair", "AIT/ETH"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "SIMULATED" in result.output
    assert "(Simulated)" in result.output


def test_exchange_orders_marks_simulated_on_network_error(mock_credentials_file, runner):
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _DeadHTTPClient):
        result = runner.invoke(exchange_island, ["orders"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "SIMULATED" in result.output
    assert "(Simulated)" in result.output


def test_exchange_rates_live_output_has_no_simulated_marker(mock_credentials_file, runner):
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _FakeHTTPClient):
        result = runner.invoke(exchange_island, ["rates"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "Simulated" not in result.output


def test_exchange_rates_table_uses_fixed_decimal_not_scientific(mock_credentials_file, runner):
    """tabulate must not re-parse pre-formatted price strings as floats (#2204)."""
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _FakeHTTPClient):
        result = runner.invoke(exchange_island, ["rates"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "0.00001260" in result.output
    assert "e-05" not in result.output


def test_exchange_orderbook_table_uses_fixed_decimal_not_scientific(mock_credentials_file, runner):
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _FakeHTTPClient):
        result = runner.invoke(exchange_island, ["orderbook", "--pair", "AIT/ETH"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "0.00001260" in result.output
    assert "e-05" not in result.output


def test_load_island_credentials_rejects_null_required_fields(tmp_path):
    """Hollow credentials (null island_id etc.) must fail at load time (#2204)."""
    import aitbc_cli.utils.island_credentials as ic_module
    from aitbc_cli.utils.island_credentials import load_island_credentials

    hollow = {
        "island_id": None,
        "island_name": None,
        "island_chain_id": None,
        "credentials": {"rpc_endpoint": "http://localhost:8202/rpc"},
    }
    cred_path = tmp_path / "island_credentials.json"
    cred_path.write_text(json.dumps(hollow))
    cred_path.chmod(0o600)

    original = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(cred_path)
    try:
        with pytest.raises(ValueError, match="island_id"):
            load_island_credentials()
    finally:
        ic_module.CREDENTIALS_PATH = original


def test_load_island_credentials_rejects_empty_string_fields(tmp_path):
    import aitbc_cli.utils.island_credentials as ic_module
    from aitbc_cli.utils.island_credentials import load_island_credentials

    hollow = {
        "island_id": "",
        "island_name": "n",
        "island_chain_id": "c",
        "credentials": {},
    }
    cred_path = tmp_path / "island_credentials.json"
    cred_path.write_text(json.dumps(hollow))
    cred_path.chmod(0o600)

    original = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(cred_path)
    try:
        with pytest.raises(ValueError, match="island_id"):
            load_island_credentials()
    finally:
        ic_module.CREDENTIALS_PATH = original


class _CancelAwareHTTPClient:
    """Returns open rows for status=open and cancel rows for status=cancelled (#2338)."""

    open_rows = [
        {
            "transaction_id": 1,
            "side": "buy",
            "max_price": 0.001,
            "amount": 1.0,
            "order_id": "ord_live",
            "pair": "AIT/ETH",
            "status": "open",
            "user_id": "0xu",
            "created_at": "2026-01-01T00:00:00",
        },
        {
            "transaction_id": 2,
            "side": "sell",
            "min_price": 0.002,
            "amount": 0.5,
            "order_id": "ord_dead",
            "pair": "AIT/ETH",
            "status": "open",
            "user_id": "0xu",
            "created_at": "2026-01-01T00:00:00",
        },
    ]
    cancel_rows = [
        {
            "transaction_id": 3,
            "action": "cancel",
            "order_id": "ord_dead",
            "status": "cancelled",
            "user_id": "0xu",
            "created_at": "2026-01-02T00:00:00",
        }
    ]

    def __init__(self, *args, **kwargs):
        pass

    def get_json(self, path, params=None, **kwargs):
        status = (params or {}).get("status")
        if status == "cancelled":
            return list(self.cancel_rows)
        if status == "open":
            return list(self.open_rows)
        return list(self.open_rows) + list(self.cancel_rows)


def test_orders_open_excludes_cancelled_orders(mock_credentials_file, runner):
    """status=open must still see cancel txs or phantom orders stay open (#2338)."""
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _CancelAwareHTTPClient):
        result = runner.invoke(exchange_island, ["orders", "--status", "open"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "ord_live" in result.output
    assert "ord_dead" not in result.output


def test_orderbook_excludes_cancelled_orders(mock_credentials_file, runner):
    from aitbc_cli.commands.exchange_island import exchange_island

    with patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient", _CancelAwareHTTPClient):
        result = runner.invoke(exchange_island, ["orderbook", "--pair", "AIT/ETH"], obj={"output_format": "table"})

    assert result.exit_code == 0
    # ord_dead was a 0.002 ask — cancelled, so best ask must come from live book only
    assert "0.0020" not in result.output


if __name__ == "__main__":
    pytest.main([__file__])
