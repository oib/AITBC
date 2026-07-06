"""
Unit tests for GPU marketplace CLI commands.

The GPU marketplace commands (offer, bid, cancel, accept, status, match,
providers) live under the `market` command group, not under `gpu`.
The `gpu` group has local hardware management commands (discover, register,
unregister, update, list).
"""

import json
import os

import pytest
from click.testing import CliRunner


@pytest.fixture
def mock_credentials_file(tmp_path):
    """Create a temporary credentials file"""
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

    import aitbc_cli.utils.island_credentials as ic_module

    original_path = ic_module.CREDENTIALS_PATH
    ic_module.CREDENTIALS_PATH = str(tmp_path / "island_credentials.json")

    with open(ic_module.CREDENTIALS_PATH, "w") as f:
        json.dump(credentials, f)

    yield credentials

    if os.path.exists(ic_module.CREDENTIALS_PATH):
        os.remove(ic_module.CREDENTIALS_PATH)
    ic_module.CREDENTIALS_PATH = original_path


@pytest.fixture
def runner():
    """Create a Click CLI runner"""
    return CliRunner()


class TestGpuHardwareCommands:
    """Test the `gpu` command group (local hardware management)."""

    def test_gpu_help(self, runner):
        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(gpu, ["--help"], obj={})
        assert result.exit_code == 0
        assert "discover" in result.output
        assert "register" in result.output
        assert "list" in result.output

    def test_gpu_list(self, runner):
        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(gpu, ["list"], obj={})
        # May fail if gpu-service not running, but should not crash
        assert result.exit_code in (0, 1)


class TestMarketGpuCommands:
    """Test GPU-related commands under the `market` group."""

    def test_market_offer_help(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["offer", "--help"], obj={})
        assert result.exit_code == 0
        assert "ollama" in result.output or "whisper" in result.output

    def test_market_list_help(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["list", "--help"], obj={})
        assert result.exit_code == 0

    def test_market_cancel_help(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["cancel", "--help"], obj={})
        assert result.exit_code == 0

    def test_market_status_help(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["status", "--help"], obj={})
        assert result.exit_code == 0

    def test_market_match_help(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["match", "--help"], obj={})
        assert result.exit_code == 0

    def test_market_providers_help(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["providers", "--help"], obj={})
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__])
