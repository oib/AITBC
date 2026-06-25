"""
Operations Commands Tests
Tests for operations CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestOperationsCommands:
    """Test operations command group"""

    def test_operations_group_exists(self):
        """Test that operations command group exists"""
        from aitbc_cli.commands.operations import operations

        assert operations is not None
        assert hasattr(operations, "name")

    def test_operations_group_name(self):
        """Test operations group name"""
        from aitbc_cli.commands.operations import operations

        assert operations.name == "operations"

    def test_operations_group_has_marketplace_subgroup(self):
        """The ``marketplace`` subgroup is registered on the operations group."""
        from aitbc_cli.commands.operations import operations

        assert "marketplace" in operations.commands

    def test_operations_group_has_ai_subgroup(self):
        """The ``ai`` subgroup is registered on the operations group."""
        from aitbc_cli.commands.operations import operations

        assert "ai" in operations.commands

    def test_operations_group_has_agent_subgroup(self):
        """The ``agent`` subgroup is registered on the operations group."""
        from aitbc_cli.commands.operations import operations

        assert "agent" in operations.commands

    def test_operations_group_has_governance_subgroup(self):
        """The ``governance`` subgroup is registered on the operations group."""
        from aitbc_cli.commands.operations import operations

        assert "governance" in operations.commands

    def test_marketplace_subgroup_has_list_listings_subcommand(self):
        """The ``list-listings`` subcommand is on the marketplace subgroup."""
        from aitbc_cli.commands.operations import operations

        marketplace = operations.commands["marketplace"]
        assert "list-listings" in marketplace.commands

    def test_ai_subgroup_has_status_subcommand(self):
        """The ``status`` subcommand is on the ai subgroup."""
        from aitbc_cli.commands.operations import operations

        ai = operations.commands["ai"]
        assert "status" in ai.commands

    def test_agent_subgroup_has_register_subcommand(self):
        """The ``register`` subcommand is on the agent subgroup."""
        from aitbc_cli.commands.operations import operations

        agent = operations.commands["agent"]
        assert "register" in agent.commands

    def test_governance_subgroup_has_execute_subcommand(self):
        """The ``execute`` subcommand is on the governance subgroup."""
        from aitbc_cli.commands.operations import operations

        governance = operations.commands["governance"]
        assert "execute" in governance.commands

    @patch("aitbc_cli.commands.operations.AITBCHTTPClient")
    def test_operations_marketplace_list_listings(self, mock_http_class, runner, mock_blockchain_rpc):
        """``operations marketplace list-listings`` lists marketplace listings."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"listings": [{"name": "item1", "price": 100}]}

        from aitbc_cli.commands.operations import operations

        result = runner.invoke(operations, ["marketplace", "list-listings"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/marketplace/listings" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.operations.AITBCHTTPClient")
    def test_operations_ai_status_all(self, mock_http_class, runner, mock_blockchain_rpc):
        """``operations ai status`` lists all AI jobs."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"jobs": [{"job_id": "job1", "state": "completed"}]}

        from aitbc_cli.commands.operations import operations

        result = runner.invoke(operations, ["ai", "status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/v1/jobs" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.operations.AITBCHTTPClient")
    def test_operations_ai_status_single(self, mock_http_class, runner, mock_blockchain_rpc):
        """``operations ai status --job-id`` gets a specific job."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"job_id": "job1", "state": "running", "progress": "50%"}

        from aitbc_cli.commands.operations import operations

        result = runner.invoke(operations, ["ai", "status", "--job-id", "job1"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/v1/jobs/job1" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.operations.AITBCHTTPClient")
    def test_operations_agent_register(self, mock_http_class, runner, mock_blockchain_rpc):
        """``operations agent register`` registers an agent via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"agent_id": "agent1", "status": "active"}

        from aitbc_cli.commands.operations import operations

        result = runner.invoke(
            operations,
            ["agent", "register", "--agent-id", "agent1", "--status", "active"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/v1/agents/register" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.operations.AITBCHTTPClient")
    @patch("aitbc_cli.commands.operations.get_config")
    def test_operations_governance_execute(self, mock_get_config, mock_http_class, runner, mock_blockchain_rpc):
        """``operations governance execute`` executes a proposal via the mocked RPC."""
        mock_get_config.return_value = MagicMock(governance_service_url="http://localhost:8105")
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "executed", "proposal_id": "prop1"}

        from aitbc_cli.commands.operations import operations

        result = runner.invoke(operations, ["governance", "execute", "prop1"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/v1/governance/proposals/prop1/execute" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.operations.AITBCHTTPClient")
    @patch("aitbc_cli.commands.operations.get_config")
    def test_operations_governance_voting_power(self, mock_get_config, mock_http_class, runner, mock_blockchain_rpc):
        """``operations governance voting-power`` queries voting power via the mocked RPC."""
        mock_get_config.return_value = MagicMock(governance_service_url="http://localhost:8105")
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"address": "ait1qtest", "voting_power": 1000}

        from aitbc_cli.commands.operations import operations

        result = runner.invoke(operations, ["governance", "voting-power", "ait1qtestaddress"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
