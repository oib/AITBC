"""
GPU Resources Commands Tests
Tests for gpu_resources CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestGPUResourcesCommands:
    """Test gpu command group"""

    def test_gpu_group_exists(self):
        """Test that gpu command group exists"""
        from aitbc_cli.commands.gpu_resources import gpu

        assert gpu is not None
        assert hasattr(gpu, "name")

    def test_gpu_group_name(self):
        """Test gpu group name"""
        from aitbc_cli.commands.gpu_resources import gpu

        assert gpu.name == "gpu-onchain"

    def test_gpu_group_has_register_subcommand(self):
        """The ``register`` subcommand is registered on the gpu group."""
        from aitbc_cli.commands.gpu_resources import gpu

        assert "register" in gpu.commands

    def test_gpu_group_has_query_subcommand(self):
        """The ``query`` subcommand is registered on the gpu group."""
        from aitbc_cli.commands.gpu_resources import gpu

        assert "query" in gpu.commands

    def test_gpu_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the gpu group."""
        from aitbc_cli.commands.gpu_resources import gpu

        assert "list" in gpu.commands

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_query_command(self, mock_get_config, mock_http_class, mock_chain_health, runner, mock_config):
        """``gpu-onchain query`` queries GPU info from the mocked blockchain RPC."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "gpu_id": "gpu-0",
            "model": "RTX 4090",
            "memory_gb": 24,
            "status": "active",
        }

        from aitbc_cli.commands.gpu_resources import gpu

        result = runner.invoke(gpu, ["query", "gpu-0"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/rpc/gpu/info/gpu-0" in called_path

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_list_command(self, mock_get_config, mock_http_class, mock_chain_health, runner, mock_config):
        """``gpu-onchain list`` lists GPUs from the mocked blockchain RPC."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = [
            {"gpu_id": "gpu-0", "model": "RTX 4090", "status": "active"},
            {"gpu_id": "gpu-1", "model": "RTX 3090", "status": "deactivated"},
        ]

        from aitbc_cli.commands.gpu_resources import gpu

        result = runner.invoke(gpu, ["list"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/rpc/gpus" in called_path

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_list_command_with_status_filter(self, mock_get_config, mock_http_class, mock_chain_health, runner, mock_config):
        """``gpu-onchain list --status`` filters GPUs by status."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = [
            {"gpu_id": "gpu-0", "model": "RTX 4090", "status": "active"},
        ]

        from aitbc_cli.commands.gpu_resources import gpu

        result = runner.invoke(gpu, ["list", "--status", "active"])

        assert result.exit_code == 0, result.output
        # Verify status param was passed.
        _, kwargs = mock_client.get.call_args
        assert kwargs.get("params", {}).get("status") == "active"

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_query_network_error_handled(self, mock_get_config, mock_http_class, mock_chain_health, runner, mock_config):
        """``gpu-onchain query`` handles NetworkError gracefully (exit 0)."""
        from aitbc_cli.commands.gpu_resources import gpu
        from aitbc_cli.utils.http_client import NetworkError

        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(gpu, ["query", "gpu-0"])

        # NetworkError is caught and reported via error(), exit code stays 0.
        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_list_network_error_handled(self, mock_get_config, mock_http_class, mock_chain_health, runner, mock_config):
        """``gpu-onchain list`` handles NetworkError gracefully (exit 0)."""
        from aitbc_cli.commands.gpu_resources import gpu
        from aitbc_cli.utils.http_client import NetworkError

        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(gpu, ["list"])

        # NetworkError is caught and reported via error(), exit code stays 0.
        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
