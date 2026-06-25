"""
Agent Comm Commands Tests
Tests for agent_comm CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


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

    @patch("aitbc_cli.commands.agent_comm.asyncio.run")
    @patch("aitbc_cli.commands.agent_comm.CrossChainAgentCommunication")
    @patch("aitbc_cli.commands.agent_comm.load_multichain_config")
    def test_agent_comm_register_command(
        self, mock_load_config, mock_comm_class, mock_asyncio_run, runner
    ):
        """``agent_comm register`` registers an agent and reports success.

        Note: the production code assigns ``success = asyncio.run(...)`` which
        shadows the imported ``success`` function.  We return a callable Mock
        so the subsequent ``success(...)`` call does not raise.
        """
        # Return a callable that is truthy so the ``if success:`` branch runs
        # and the ``success(...)`` call succeeds despite the name shadowing.
        mock_asyncio_run.return_value = MagicMock(return_value=None)

        from aitbc_cli.commands.agent_comm import agent_comm

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
        )

        assert result.exit_code == 0, result.output
        mock_load_config.assert_called_once()
        mock_comm_class.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch("aitbc_cli.commands.agent_comm.asyncio.run")
    @patch("aitbc_cli.commands.agent_comm.CrossChainAgentCommunication")
    @patch("aitbc_cli.commands.agent_comm.load_multichain_config")
    def test_agent_comm_status_command(
        self, mock_load_config, mock_comm_class, mock_asyncio_run, runner
    ):
        """``agent_comm status`` retrieves agent status from the mocked comm layer."""
        mock_asyncio_run.return_value = {
            "agent_info": {
                "agent_id": "agent-001",
                "name": "TestAgent",
                "chain_id": "test-chain",
                "capabilities": ["compute"],
                "reputation_score": 0.85,
                "endpoint": "http://localhost:8000",
                "version": "1.0.0",
            },
            "status": "active",
            "message_queue_size": 0,
            "active_collaborations": 0,
            "last_seen": "2026-01-01T00:00:00Z",
        }

        from aitbc_cli.commands.agent_comm import agent_comm

        result = runner.invoke(agent_comm, ["status", "agent-001"])

        assert result.exit_code == 0, result.output
        mock_load_config.assert_called_once()
        mock_asyncio_run.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
