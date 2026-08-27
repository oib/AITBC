"""Tests for the aitbc sync command group."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestSyncCommands:
    """Test sync command group."""

    def test_sync_group_exists(self):
        from aitbc_cli.commands.sync import sync

        assert sync is not None
        assert sync.name == "sync"
        assert "status" in sync.commands
        assert "bulk" in sync.commands

    @patch("aitbc_cli.commands.sync.AITBCHTTPClient")
    def test_sync_status_shows_divergence(self, mock_http_class, runner):
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = [
            # local head
            {"height": 100, "hash": "0xlocalhash", "timestamp": "2026-08-21T00:00:00", "tx_count": 5},
            # network info
            {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"], "chain_id": "ait"},
            # sync config (missing/old endpoint)
            {"error": "not found"},
            # hub head
            {"height": 110, "hash": "0xhubhash", "timestamp": "2026-08-21T00:01:00", "tx_count": 10},
            # hub network info
            {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"]},
        ]

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(
            sync,
            ["status", "--node-url", "http://localhost:8202", "--hub-url", "http://hub:8202"],
        )

        assert result.exit_code == 0, result.output
        assert "Hub height" in result.output
        assert "10" in result.output
        assert "BEHIND_BY_10" in result.output

    @patch("aitbc_cli.commands.sync.AITBCHTTPClient")
    def test_sync_status_hash_mismatch(self, mock_http_class, runner):
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = [
            {"height": 110, "hash": "0xlocalhash", "timestamp": "2026-08-21T00:00:00", "tx_count": 5},
            {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"], "chain_id": "ait"},
            {"error": "not found"},
            {"height": 110, "hash": "0xhubhash", "timestamp": "2026-08-21T00:01:00", "tx_count": 10},
            {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"]},
        ]

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(
            sync,
            ["status", "--node-url", "http://localhost:8202", "--hub-url", "http://hub:8202"],
        )

        assert result.exit_code == 0, result.output
        assert "HASH_MISMATCH" in result.output

    @patch("aitbc_cli.commands.sync.AITBCHTTPClient")
    def test_sync_status_alert_exits_nonzero(self, mock_http_class, runner):
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = [
            {"height": 100, "hash": "0xlocalhash", "timestamp": "2026-08-21T00:00:00", "tx_count": 5},
            {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"], "chain_id": "ait"},
            {"error": "not found"},
            {"height": 110, "hash": "0xhubhash", "timestamp": "2026-08-21T00:01:00", "tx_count": 10},
            {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"]},
        ]

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(
            sync,
            [
                "status",
                "--node-url",
                "http://localhost:8202",
                "--hub-url",
                "http://hub:8202",
                "--alert",
            ],
        )

        assert result.exit_code == 1
        assert "BEHIND_BY_10" in result.output

    @patch("aitbc_cli.commands.sync.AITBCHTTPClient")
    def test_sync_status_hub_unreachable(self, mock_http_class, runner):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value

        def side_effect(path, **kwargs):
            if path == "/rpc/head" and "hub" in str(kwargs.get("params")):
                # This path is not reached with the same mock because both clients share it.
                raise NetworkError("hub down")
            if "/rpc/head" in path:
                return {"height": 100, "hash": "0xlocalhash", "timestamp": "2026-08-21T00:00:00", "tx_count": 5}
            if "/rpc/network-info" in path:
                return {"p2p_endpoint": "0.0.0.0:8200", "supported_chains": ["ait"], "chain_id": "ait"}
            if "/rpc/sync/config" in path:
                return {"error": "not found"}
            return {}

        mock_client.get.side_effect = side_effect

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(
            sync,
            ["status", "--node-url", "http://localhost:8202", "--hub-url", "http://hub:8202"],
        )

        assert result.exit_code == 0, result.output
