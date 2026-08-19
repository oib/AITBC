"""
Agent Comm Commands Tests
Tests for agent_comm CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest

from tests.fixtures.cli_mocks import make_cli_obj


class TestAgentCommCommands:
    """Test agent_comm command group"""

    def test_agent_comm_group_exists(self):
        """Test that agent_comm command group exists"""
        from aitbc_cli.commands.agent_comm import agent_comm

        assert agent_comm is not None
        assert hasattr(agent_comm, "name")

    def test_agent_comm_group_name(self):
        """Test agent_comm group name"""
        from aitbc_cli.commands.agent_comm import agent_comm

        assert agent_comm.name == "agent-comm"

    def test_agent_comm_group_has_register_subcommand(self):
        """The ``register`` subcommand is registered on the agent_comm group."""
        from aitbc_cli.commands.agent_comm import agent_comm

        assert "register" in agent_comm.commands

    def test_agent_comm_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the agent_comm group."""
        from aitbc_cli.commands.agent_comm import agent_comm

        assert "list" in agent_comm.commands

    @patch("aitbc_cli.commands.agent_comm.AITBCHTTPClient")
    def test_agent_comm_register_command(self, mock_http_class, runner, mock_config):
        """``agent_comm register`` posts to the agent-coordinator."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {
            "status": "success",
            "agent_id": "agent-001",
        }

        from aitbc_cli.commands.agent_comm import agent_comm

        obj = make_cli_obj()
        obj["config"] = mock_config
        result = runner.invoke(
            agent_comm,
            [
                "register",
                "agent-001",
                "TestAgent",
                "test-chain",
                "http://localhost:8000",
                "--capabilities",
                "compute,storage",
                "--reputation",
                "0.8",
            ],
            obj=obj,
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        posted_path = mock_client.post.call_args[0][0]
        posted_body = mock_client.post.call_args.kwargs.get("json")
        assert "/v1/agents/register" == posted_path
        assert posted_body["agent_id"] == "agent-001"
        assert posted_body["capabilities"] == ["compute", "storage"]
        assert posted_body["chain_id"] == "test-chain"

    @patch("aitbc_cli.commands.agent_comm.AITBCHTTPClient")
    def test_agent_comm_status_command(self, mock_http_class, runner, mock_config):
        """``agent_comm status`` fetches an agent from the agent-coordinator."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "agent": {
                "agent_id": "agent-001",
                "name": "TestAgent",
                "chain_id": "test-chain",
                "capabilities": ["compute"],
                "reputation": 0.85,
                "status": "active",
                "last_heartbeat": "2026-01-01T00:00:00Z",
                "endpoints": {"http": "http://localhost:8000"},
                "metadata": {"version": "1.0.0"},
            }
        }

        from aitbc_cli.commands.agent_comm import agent_comm

        obj = make_cli_obj()
        obj["config"] = mock_config
        result = runner.invoke(agent_comm, ["status", "agent-001"], obj=obj)

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/v1/agents/agent-001" == mock_client.get.call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
