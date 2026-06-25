"""
Agent SDK Commands Tests
Tests for agent_sdk CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestAgentSDKCommands:
    """Test agent command group"""

    def test_agent_group_exists(self):
        """Test that agent command group exists"""
        from aitbc_cli.commands.agent_sdk import agent

        assert agent is not None
        assert hasattr(agent, "name")

    def test_agent_group_name(self):
        """Test agent group name"""
        from aitbc_cli.commands.agent_sdk import agent

        assert agent.name == "agent"

    def test_agent_group_has_create_subcommand(self):
        """The ``create`` subcommand is registered on the agent group."""
        from aitbc_cli.commands.agent_sdk import agent

        assert "create" in agent.commands

    def test_agent_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the agent group."""
        from aitbc_cli.commands.agent_sdk import agent

        assert "list" in agent.commands

    @patch("aitbc_cli.commands.agent_sdk.create_agent")
    def test_agent_create_command(self, mock_create_agent, runner):
        """``agent create`` creates a new agent via the mocked SDK helper.

        The original ``init`` subcommand was never implemented; ``create`` is
        the equivalent subcommand on the ``agent_sdk`` agent group.
        """
        mock_create_agent.return_value = {
            "success": True,
            "agent_id": "agent-test-001",
            "name": "test-agent",
            "address": "0xTestAddress0000000000000000000000000000000",
            "agent_type": "provider",
            "config_file": "/tmp/test-agent.json",
        }

        from aitbc_cli.commands.agent_sdk import agent

        result = runner.invoke(
            agent,
            ["create", "test-agent", "--type", "provider"],
        )

        assert result.exit_code == 0, result.output
        mock_create_agent.assert_called_once()

    @patch("aitbc_cli.commands.agent_sdk.list_local_agents")
    def test_agent_list_command(self, mock_list_local_agents, runner):
        """``agent list`` lists locally stored agent configurations."""
        mock_list_local_agents.return_value = []

        from aitbc_cli.commands.agent_sdk import agent

        result = runner.invoke(agent, ["list"])

        assert result.exit_code == 0, result.output
        mock_list_local_agents.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
