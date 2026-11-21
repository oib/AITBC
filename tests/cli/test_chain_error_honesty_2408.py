"""#2408: chain-management commands fail cleanly on unknown ids and unimplemented endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc_cli.core.chain_manager import ChainNotFoundError, NodeNotAvailableError
from aitbc_cli.core.config import NodeConfig
from aitbc_cli.core.node_client import NodeClient


class TestChainErrorHonesty:
    """Unknown chain/node ids abort with a one-line error, not a traceback."""

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_backup_unknown_node_clean_error(self, mock_load_config, mock_manager_cls, mock_run, runner):
        mock_manager_cls.return_value.backup_chain.side_effect = NodeNotAvailableError("No nodes available")

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["backup", "--chain-id", "bc-2"])

        assert result.exit_code != 0
        assert "No nodes available" in result.output
        assert "Traceback" not in result.output

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_add_unknown_node_clean_error(self, mock_load_config, mock_manager_cls, mock_run, runner):
        mock_manager_cls.return_value.add_chain_to_node.side_effect = NodeNotAvailableError(
            "Node node-9 not configured"
        )

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["add", "--chain-id", "bc-2", "--node-id", "node-9"])

        assert result.exit_code != 0
        assert "Node node-9 not configured" in result.output
        assert "Traceback" not in result.output

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_remove_unknown_chain_clean_error(self, mock_load_config, mock_manager_cls, mock_run, runner):
        mock_manager_cls.return_value.remove_chain_from_node.side_effect = ChainNotFoundError(
            "Chain bc-2 not found"
        )

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["remove", "--chain-id", "bc-2", "--node-id", "local-rpc"])

        assert result.exit_code != 0
        assert "Chain bc-2 not found" in result.output
        assert "Traceback" not in result.output

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_migrate_unknown_node_clean_error(self, mock_load_config, mock_manager_cls, mock_run, runner):
        mock_manager_cls.return_value.migrate_chain.side_effect = NodeNotAvailableError(
            "Source node node-a not configured"
        )

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(
            chain, ["migrate", "--chain-id", "bc-2", "--from-node", "node-a", "--to-node", "node-b"]
        )

        assert result.exit_code != 0
        assert "Source node node-a not configured" in result.output
        assert "Traceback" not in result.output

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_restore_unknown_node_clean_error(self, mock_load_config, mock_manager_cls, mock_run, runner, tmp_path):
        backup = tmp_path / "b.tar.gz"
        backup.write_bytes(b"x")
        mock_manager_cls.return_value.restore_chain.side_effect = NodeNotAvailableError("No nodes available")

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["restore", "--backup-file", str(backup)])

        assert result.exit_code != 0
        assert "No nodes available" in result.output
        assert "Traceback" not in result.output


class TestNodeClientBackup404:
    """A node without the backup/restore routes fails with a clear message."""

    def _client(self) -> NodeClient:
        client = NodeClient(NodeConfig(id="n1", endpoint="http://127.0.0.1:8202"))
        response = MagicMock()
        response.status_code = 404
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=response)
        return client

    @pytest.mark.asyncio
    async def test_backup_404_names_missing_route(self):
        client = self._client()
        with pytest.raises(RuntimeError, match="does not implement chain backup"):
            await client.backup_chain("bc-2", "/tmp/bk")

    @pytest.mark.asyncio
    async def test_restore_404_names_missing_route(self):
        client = self._client()
        with pytest.raises(RuntimeError, match="does not implement chain restore"):
            await client.restore_chain("/tmp/bk.tar")
