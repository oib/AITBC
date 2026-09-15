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

        result = runner.invoke(gpu, ["query", "--gpu-id", "gpu-0"])

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
    def test_gpu_list_command_with_status_filter(
        self, mock_get_config, mock_http_class, mock_chain_health, runner, mock_config
    ):
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

        result = runner.invoke(gpu, ["query", "--gpu-id", "gpu-0"])

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

    @patch("aitbc_cli.utils.gpu_onchain.wait_for_tx")
    @patch("aitbc_cli.utils.gpu_onchain.submit_gpu_register")
    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_register_wait_reports_mined(
        self, mock_get_config, mock_chain_health, mock_submit, mock_wait, runner, mock_config, cli_obj
    ):
        """``gpu-onchain register --wait`` reports the mined block height."""
        mock_get_config.return_value = mock_config
        mock_submit.return_value = {"transaction_hash": "0xabc123"}
        mock_wait.return_value = {"block_height": 7210, "tx_hash": "0xabc123"}

        from aitbc_cli.commands.gpu_resources import gpu

        result = runner.invoke(
            gpu,
            [
                "register",
                "--gpu-id",
                "gpu-0",
                "--miner-id",
                "miner-0",
                "--model",
                "RTX 4090",
                "--memory-gb",
                "24",
                "--price-per-hour",
                "10",
                "--wallet",
                "w1",
                "--wait",
            ],
            obj=cli_obj,
        )

        assert result.exit_code == 0, result.output
        mock_wait.assert_called_once()
        assert mock_wait.call_args[0][1] == "0xabc123"
        assert "7210" in result.output

    @patch("aitbc_cli.utils.gpu_onchain.wait_for_tx", return_value=None)
    @patch("aitbc_cli.utils.gpu_onchain.submit_gpu_register")
    @patch("aitbc_cli.utils.chain_id.get_chain_id_from_health", return_value="test-chain")
    @patch("aitbc_cli.commands.gpu_resources.get_config")
    def test_gpu_register_wait_timeout_reports_unmined(
        self, mock_get_config, mock_chain_health, mock_submit, mock_wait, runner, mock_config, cli_obj
    ):
        """``gpu-onchain register --wait`` reports mined=false on timeout instead of crashing."""
        mock_get_config.return_value = mock_config
        mock_submit.return_value = {"transaction_hash": "0xabc123"}

        from aitbc_cli.commands.gpu_resources import gpu

        result = runner.invoke(
            gpu,
            [
                "register",
                "--gpu-id",
                "gpu-0",
                "--miner-id",
                "miner-0",
                "--model",
                "RTX 4090",
                "--memory-gb",
                "24",
                "--price-per-hour",
                "10",
                "--wallet",
                "w1",
                "--wait",
            ],
            obj=cli_obj,
        )

        assert result.exit_code == 0, result.output
        assert '"mined": false' in result.output


class TestWaitForTx:
    """Tests for the ``wait_for_tx`` confirmation poll (GAP-41 regression).

    ``/rpc/transaction/{hash}`` 404s while the tx is still in the mempool; the
    old implementation ran those polls through ``AITBCHTTPClient`` whose
    circuit breaker opened after five 404s. The poll now uses plain requests.
    """

    def test_wait_for_tx_returns_on_mined(self):
        """A mined transaction (200 + block_height) is returned immediately."""
        from unittest.mock import MagicMock

        from aitbc_cli.utils.gpu_onchain import wait_for_tx

        mined = MagicMock()
        mined.status_code = 200
        mined.json.return_value = {"tx_hash": "0xabc", "block_height": 42}

        with patch("requests.get", side_effect=[_not_found(), _not_found(), mined]) as mock_get:
            result = wait_for_tx("http://node:8202", "0xabc", timeout=5.0, poll_interval=0.01)

        assert result == {"tx_hash": "0xabc", "block_height": 42}
        assert mock_get.call_count == 3
        assert mock_get.call_args[0][0] == "http://node:8202/rpc/transaction/0xabc"

    def test_wait_for_tx_tolerates_pending_404s(self):
        """Sustained 404s must not trip a circuit breaker — poll until timeout."""
        from aitbc_cli.utils.gpu_onchain import wait_for_tx

        with patch("requests.get", side_effect=_always_not_found) as mock_get:
            result = wait_for_tx("http://node:8202", "0xabc", timeout=0.15, poll_interval=0.01)

        assert result is None
        # More than the old circuit-breaker threshold of 5 failures.
        assert mock_get.call_count > 5

    def test_wait_for_tx_tolerates_connection_errors(self):
        """Transient connection errors are interim failures, not a poll abort."""
        import requests as _requests

        from aitbc_cli.utils.gpu_onchain import wait_for_tx

        with patch("requests.get", side_effect=_requests.ConnectionError("refused")):
            result = wait_for_tx("http://node:8202", "0xabc", timeout=0.1, poll_interval=0.01)

        assert result is None


def _not_found():
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = 404
    return resp


def _always_not_found(*args, **kwargs):
    return _not_found()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
