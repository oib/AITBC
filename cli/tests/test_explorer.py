"""
Unit tests for Blockchain Explorer CLI commands.

Tests cover all 14 explorer subcommands using Click's CliRunner and mocking
the AITBCHTTPClient to avoid real network calls.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_client():
    """Mock the explorer HTTP client returned by get_explorer_client()."""
    client = MagicMock()
    client.get.return_value = {}
    with patch("aitbc_cli.commands.explorer.get_explorer_client", return_value=client):
        yield client


# ---------------------------------------------------------------------------
# Group help
# ---------------------------------------------------------------------------


def test_explorer_group_help(runner):
    """The explorer group should list all subcommands in --help."""
    from aitbc_cli.commands.explorer import explorer

    result = runner.invoke(explorer, ["--help"])
    assert result.exit_code == 0
    assert "Blockchain Explorer commands" in result.output
    for cmd in [
        "chain-head",
        "latest-blocks",
        "non-empty-blocks",
        "block",
        "block-by-hash",
        "transaction",
        "transaction-by-hash",
        "search-transactions",
        "blocks-by-address",
        "activity-timeline",
        "network-stats",
        "provider-reputation",
        "top-addresses",
        "chains",
    ]:
        assert cmd in result.output, f"Missing {cmd} in help output"


# ---------------------------------------------------------------------------
# chain-head
# ---------------------------------------------------------------------------


def test_chain_head_success(runner, mock_client):
    """chain-head should display the head block JSON."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"height": 42, "hash": "0xabc"}
    result = runner.invoke(explorer, ["chain-head"])
    assert result.exit_code == 0
    assert "Chain Head" in result.output
    assert '"height": 42' in result.output
    mock_client.get.assert_called_once_with("/api/chain/head", params={})


def test_chain_head_with_chain_id(runner, mock_client):
    """chain-head --chain-id should pass chain_id as param."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"height": 1}
    result = runner.invoke(explorer, ["chain-head", "--chain-id", "ait-test"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/chain/head", params={"chain_id": "ait-test"})


def test_chain_head_empty(runner, mock_client):
    """chain-head with no data should show error message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["chain-head"])
    assert result.exit_code == 0
    assert "No chain head data available" in result.output


def test_chain_head_network_error(runner, mock_client):
    """chain-head should handle NetworkError gracefully."""
    from aitbc_cli.commands.explorer import explorer
    from aitbc_cli.utils.http_client import NetworkError

    mock_client.get.side_effect = NetworkError("connection refused")
    result = runner.invoke(explorer, ["chain-head"])
    assert result.exit_code == 0
    assert "Explorer API unavailable" in result.output


# ---------------------------------------------------------------------------
# latest-blocks
# ---------------------------------------------------------------------------


def test_latest_blocks_success(runner, mock_client):
    """latest-blocks should display block list."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"blocks": [{"height": 1}, {"height": 2}]}
    result = runner.invoke(explorer, ["latest-blocks"])
    assert result.exit_code == 0
    assert "Latest 2 blocks" in result.output
    mock_client.get.assert_called_once_with("/api/blocks/latest", params={"limit": 10, "offset": 0})


def test_latest_blocks_with_options(runner, mock_client):
    """latest-blocks --limit --offset --chain-id should pass all params."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"blocks": []}
    result = runner.invoke(explorer, ["latest-blocks", "--limit", "5", "--offset", "10", "--chain-id", "ait-test"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/blocks/latest", params={"limit": 5, "offset": 10, "chain_id": "ait-test"})


def test_latest_blocks_network_error(runner, mock_client):
    """latest-blocks should handle NetworkError."""
    from aitbc_cli.commands.explorer import explorer
    from aitbc_cli.utils.http_client import NetworkError

    mock_client.get.side_effect = NetworkError("timeout")
    result = runner.invoke(explorer, ["latest-blocks"])
    assert result.exit_code == 0
    assert "Explorer API unavailable" in result.output


# ---------------------------------------------------------------------------
# non-empty-blocks
# ---------------------------------------------------------------------------


def test_non_empty_blocks_success(runner, mock_client):
    """non-empty-blocks should display blocks with transactions."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"blocks": [{"height": 5}]}
    result = runner.invoke(explorer, ["non-empty-blocks"])
    assert result.exit_code == 0
    assert "Non-empty blocks: 1" in result.output
    mock_client.get.assert_called_once_with("/api/blocks/non-empty", params={"limit": 10, "offset": 0})


def test_non_empty_blocks_with_chain_id(runner, mock_client):
    """non-empty-blocks --chain-id should include chain_id param."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"blocks": []}
    result = runner.invoke(explorer, ["non-empty-blocks", "--chain-id", "ait-hub"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/blocks/non-empty", params={"limit": 10, "offset": 0, "chain_id": "ait-hub"})


# ---------------------------------------------------------------------------
# block (by height)
# ---------------------------------------------------------------------------


def test_block_success(runner, mock_client):
    """block HEIGHT should display block data."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"height": 100, "hash": "0xdef"}
    result = runner.invoke(explorer, ["block", "100"])
    assert result.exit_code == 0
    assert "Block at height 100" in result.output
    mock_client.get.assert_called_once_with("/api/blocks/100", params={})


def test_block_not_found(runner, mock_client):
    """block with no result should show not-found message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["block", "999"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_block_with_chain_id(runner, mock_client):
    """block --chain-id should include chain_id param."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"height": 1}
    result = runner.invoke(explorer, ["block", "1", "--chain-id", "ait-test"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/blocks/1", params={"chain_id": "ait-test"})


# ---------------------------------------------------------------------------
# block-by-hash
# ---------------------------------------------------------------------------


def test_block_by_hash_success(runner, mock_client):
    """block-by-hash HASH should display block data."""
    from aitbc_cli.commands.explorer import explorer

    test_hash = "0xabcdef1234567890"
    mock_client.get.return_value = {"hash": test_hash, "height": 50}
    result = runner.invoke(explorer, ["block-by-hash", test_hash])
    assert result.exit_code == 0
    assert f"Block with hash {test_hash}" in result.output
    mock_client.get.assert_called_once_with(f"/api/blocks/by-hash/{test_hash}", params={})


def test_block_by_hash_not_found(runner, mock_client):
    """block-by-hash with no result should show not-found message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["block-by-hash", "0xmissing"])
    assert result.exit_code == 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# transaction (alias for transaction-by-hash)
# ---------------------------------------------------------------------------


def test_transaction_success(runner, mock_client):
    """transaction HASH should display transaction data."""
    from aitbc_cli.commands.explorer import explorer

    test_hash = "0xtx123456"
    mock_client.get.return_value = {"hash": test_hash, "amount": 100}
    result = runner.invoke(explorer, ["transaction", test_hash])
    assert result.exit_code == 0
    assert f"Transaction {test_hash}" in result.output
    mock_client.get.assert_called_once_with(f"/api/transactions/by-hash/{test_hash}", params={})


def test_transaction_not_found(runner, mock_client):
    """transaction with no result should show not-found message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["transaction", "0xmissing"])
    assert result.exit_code == 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# transaction-by-hash
# ---------------------------------------------------------------------------


def test_transaction_by_hash_success(runner, mock_client):
    """transaction-by-hash HASH should display full transaction details."""
    from aitbc_cli.commands.explorer import explorer

    test_hash = "0xtx789"
    mock_client.get.return_value = {"hash": test_hash, "sender": "0xaaa", "recipient": "0xbbb"}
    result = runner.invoke(explorer, ["transaction-by-hash", test_hash])
    assert result.exit_code == 0
    assert f"Transaction details for {test_hash}" in result.output
    mock_client.get.assert_called_once_with(f"/api/transactions/by-hash/{test_hash}", params={})


def test_transaction_by_hash_not_found(runner, mock_client):
    """transaction-by-hash with no result should show not-found message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["transaction-by-hash", "0xmissing"])
    assert result.exit_code == 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# search-transactions
# ---------------------------------------------------------------------------


def test_search_transactions_success(runner, mock_client):
    """search-transactions ADDRESS should display matching transactions."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"transactions": [{"hash": "0xtx1"}, {"hash": "0xtx2"}]}
    result = runner.invoke(explorer, ["search-transactions", "0xaddr123"])
    assert result.exit_code == 0
    assert "Found 2 transactions for 0xaddr123" in result.output
    mock_client.get.assert_called_once_with("/api/transactions/search", params={"address": "0xaddr123", "limit": 100})


def test_search_transactions_with_limit(runner, mock_client):
    """search-transactions --limit should pass custom limit."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"transactions": []}
    result = runner.invoke(explorer, ["search-transactions", "0xaddr", "--limit", "10"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/transactions/search", params={"address": "0xaddr", "limit": 10})


def test_search_transactions_with_chain_id(runner, mock_client):
    """search-transactions --chain-id should include chain_id param."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"transactions": []}
    result = runner.invoke(explorer, ["search-transactions", "0xaddr", "--chain-id", "ait-test"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with(
        "/api/transactions/search",
        params={"address": "0xaddr", "limit": 100, "chain_id": "ait-test"},
    )


# ---------------------------------------------------------------------------
# blocks-by-address
# ---------------------------------------------------------------------------


def test_blocks_by_address_success(runner, mock_client):
    """blocks-by-address ADDRESS should display matching blocks."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"blocks": [{"height": 1}, {"height": 2}, {"height": 3}]}
    result = runner.invoke(explorer, ["blocks-by-address", "0xaddr456"])
    assert result.exit_code == 0
    assert "Found 3 blocks for 0xaddr456" in result.output
    mock_client.get.assert_called_once_with("/api/blocks/by-address/0xaddr456", params={"address": "0xaddr456", "limit": 50})


def test_blocks_by_address_with_limit(runner, mock_client):
    """blocks-by-address --limit should pass custom limit."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"blocks": []}
    result = runner.invoke(explorer, ["blocks-by-address", "0xaddr", "--limit", "5"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/blocks/by-address/0xaddr", params={"address": "0xaddr", "limit": 5})


# ---------------------------------------------------------------------------
# activity-timeline
# ---------------------------------------------------------------------------


def test_activity_timeline_success(runner, mock_client):
    """activity-timeline should display timeline data."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"timeline": [{"date": "2026-01-01", "count": 42}]}
    result = runner.invoke(explorer, ["activity-timeline"])
    assert result.exit_code == 0
    assert "Activity timeline for 24h" in result.output
    mock_client.get.assert_called_once_with("/api/analytics/activity", params={"period": "24h"})


def test_activity_timeline_custom_period(runner, mock_client):
    """activity-timeline --period should pass custom period."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"timeline": []}
    result = runner.invoke(explorer, ["activity-timeline", "--period", "7d"])
    assert result.exit_code == 0
    assert "Activity timeline for 7d" in result.output
    mock_client.get.assert_called_once_with("/api/analytics/activity", params={"period": "7d"})


def test_activity_timeline_empty(runner, mock_client):
    """activity-timeline with no data should show error message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["activity-timeline"])
    assert result.exit_code == 0
    assert "No activity data available" in result.output


# ---------------------------------------------------------------------------
# network-stats
# ---------------------------------------------------------------------------


def test_network_stats_success(runner, mock_client):
    """network-stats should display network statistics."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"total_ait": 1000000, "active_offers": 42, "unique_nodes": 10}
    result = runner.invoke(explorer, ["network-stats"])
    assert result.exit_code == 0
    assert "Network Statistics" in result.output
    mock_client.get.assert_called_once_with("/api/analytics/network-stats", params={})


def test_network_stats_with_chain_id(runner, mock_client):
    """network-stats --chain-id should include chain_id param."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"total_ait": 500}
    result = runner.invoke(explorer, ["network-stats", "--chain-id", "ait-test"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/analytics/network-stats", params={"chain_id": "ait-test"})


def test_network_stats_empty(runner, mock_client):
    """network-stats with no data should show error message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["network-stats"])
    assert result.exit_code == 0
    assert "No network stats available" in result.output


# ---------------------------------------------------------------------------
# provider-reputation
# ---------------------------------------------------------------------------


def test_provider_reputation_success(runner, mock_client):
    """provider-reputation PROVIDER_ID should display reputation data."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"provider_id": "node-1", "score": 95, "uptime": 99.9}
    result = runner.invoke(explorer, ["provider-reputation", "node-1"])
    assert result.exit_code == 0
    assert "Reputation for provider node-1" in result.output
    mock_client.get.assert_called_once_with("/api/analytics/provider-reputation/node-1", params={})


def test_provider_reputation_with_chain_id(runner, mock_client):
    """provider-reputation --chain-id should include chain_id param."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"score": 80}
    result = runner.invoke(explorer, ["provider-reputation", "node-2", "--chain-id", "ait-test"])
    assert result.exit_code == 0
    mock_client.get.assert_called_once_with("/api/analytics/provider-reputation/node-2", params={"chain_id": "ait-test"})


def test_provider_reputation_not_found(runner, mock_client):
    """provider-reputation with no data should show error message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["provider-reputation", "unknown-provider"])
    assert result.exit_code == 0
    assert "No reputation data for provider" in result.output


# ---------------------------------------------------------------------------
# top-addresses
# ---------------------------------------------------------------------------


def test_top_addresses_success(runner, mock_client):
    """top-addresses should display top addresses by activity."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"addresses": [{"address": "0xaaa", "tx_count": 100}]}
    result = runner.invoke(explorer, ["top-addresses"])
    assert result.exit_code == 0
    assert "Top 1 addresses" in result.output
    mock_client.get.assert_called_once_with("/api/analytics/top-addresses", params={"limit": 20})


def test_top_addresses_with_limit(runner, mock_client):
    """top-addresses --limit should pass custom limit."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"addresses": [{"address": "0xbbb"}, {"address": "0xccc"}]}
    result = runner.invoke(explorer, ["top-addresses", "--limit", "50"])
    assert result.exit_code == 0
    assert "Top 2 addresses" in result.output
    mock_client.get.assert_called_once_with("/api/analytics/top-addresses", params={"limit": 50})


def test_top_addresses_empty(runner, mock_client):
    """top-addresses with empty list should show count 0."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = {"addresses": []}
    result = runner.invoke(explorer, ["top-addresses"])
    assert result.exit_code == 0
    assert "Top 0 addresses" in result.output


# ---------------------------------------------------------------------------
# chains
# ---------------------------------------------------------------------------


def test_chains_success(runner, mock_client):
    """chains should display all supported chains."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = [{"chain_id": "ait-hub", "height": 1000}]
    result = runner.invoke(explorer, ["chains"])
    assert result.exit_code == 0
    assert "Supported Chains" in result.output
    mock_client.get.assert_called_once_with("/api/chains")


def test_chains_empty(runner, mock_client):
    """chains with no data should show error message."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.return_value = None
    result = runner.invoke(explorer, ["chains"])
    assert result.exit_code == 0
    assert "No chains data available" in result.output


# ---------------------------------------------------------------------------
# Generic error handling
# ---------------------------------------------------------------------------


def test_generic_exception_handled(runner, mock_client):
    """Any unexpected exception should be caught and displayed via error()."""
    from aitbc_cli.commands.explorer import explorer

    mock_client.get.side_effect = RuntimeError("unexpected")
    result = runner.invoke(explorer, ["chain-head"])
    assert result.exit_code == 0
    assert "Error getting chain head" in result.output


if __name__ == "__main__":
    pytest.main([__file__])
