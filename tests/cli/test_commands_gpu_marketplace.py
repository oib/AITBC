"""
GPU Marketplace Commands Tests
Tests for gpu_marketplace CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestGPUMarketplaceCommands:
    """Test gpu command group"""

    def test_gpu_group_exists(self):
        """Test that gpu command group exists"""
        from aitbc_cli.commands.gpu_marketplace import gpu

        assert gpu is not None
        assert hasattr(gpu, "name")

    def test_gpu_group_name(self):
        """Test gpu group name"""
        from aitbc_cli.commands.gpu_marketplace import gpu

        assert gpu.name == "gpu"

    def test_gpu_group_has_discover_subcommand(self):
        """The ``discover`` subcommand is registered on the gpu group."""
        from aitbc_cli.commands.gpu_marketplace import gpu

        assert "discover" in gpu.commands

    def test_gpu_group_has_register_subcommand(self):
        """The ``register`` subcommand is registered on the gpu group."""
        from aitbc_cli.commands.gpu_marketplace import gpu

        assert "register" in gpu.commands

    def test_gpu_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the gpu group."""
        from aitbc_cli.commands.gpu_marketplace import gpu

        assert "list" in gpu.commands

    @patch("aitbc_cli.commands.gpu_marketplace.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_marketplace.get_config")
    def test_gpu_discover_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``gpu discover`` auto-discovers GPU specs via the mocked GPU service."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"gpus": [{"id": "gpu-0", "model": "RTX 4090", "memory_gb": 24}]}

        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(gpu, ["discover"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/v1/gpu/discover" in called_path

    @patch("aitbc_cli.commands.gpu_marketplace.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_marketplace.get_config")
    def test_gpu_register_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``gpu register`` registers a GPU via the mocked GPU service."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"gpu_id": "gpu-0", "status": "registered"}

        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(gpu, ["register", "gpu-0"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        called_path = mock_client.post.call_args[0][0]
        assert "/v1/gpu/register" in called_path

    @patch("aitbc_cli.commands.gpu_marketplace.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_marketplace.get_config")
    def test_gpu_register_command_with_specs(self, mock_get_config, mock_http_class, runner, mock_config):
        """``gpu register --specs`` passes JSON specs to the GPU service."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"gpu_id": "gpu-0", "status": "registered"}

        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(
            gpu,
            ["register", "gpu-0", "--specs", '{"model": "RTX 4090", "memory_gb": 24}'],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()

    @patch("aitbc_cli.commands.gpu_marketplace.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_marketplace.get_config")
    def test_gpu_discover_network_error_handled(self, mock_get_config, mock_http_class, runner, mock_config):
        """``gpu discover`` handles NetworkError gracefully (exit 0)."""
        from aitbc_cli.commands.gpu_marketplace import gpu
        from aitbc_cli.utils.http_client import NetworkError

        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(gpu, ["discover"])

        # NetworkError is caught and reported via error(), exit code stays 0.
        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.gpu_marketplace.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_marketplace.get_config")
    def test_gpu_list_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``gpu list`` lists registered GPUs from the mocked GPU service."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = [
            {"id": "gpu-0", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": 0.5, "status": "active"},
        ]

        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(gpu, ["list"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()

    @patch("aitbc_cli.commands.gpu_marketplace.AITBCHTTPClient")
    @patch("aitbc_cli.commands.gpu_marketplace.get_config")
    def test_gpu_list_command_empty(self, mock_get_config, mock_http_class, runner, mock_config):
        """``gpu list`` handles an empty GPU list gracefully."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = []

        from aitbc_cli.commands.gpu_marketplace import gpu

        result = runner.invoke(gpu, ["list"])

        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
