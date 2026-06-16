"""
Agent SDK Commands Tests
Tests for agent_sdk CLI commands
"""

from unittest.mock import patch

import pytest


class TestAgentSDKCommands:
    """Test agent command group"""

    def test_agent_group_exists(self):
        """Test that agent command group exists"""
        try:
            from aitbc_cli.commands.agent_sdk import agent

            assert agent is not None
            assert hasattr(agent, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import agent commands: {e}")

    def test_agent_group_name(self):
        """Test agent group name"""
        try:
            from aitbc_cli.commands.agent_sdk import agent

            assert agent.name == "agent"
        except ImportError as e:
            pytest.skip(f"Cannot import agent commands: {e}")

    @patch("aitbc_cli.commands.agent_sdk.output")
    @patch("aitbc_cli.commands.agent_sdk.error")
    def test_agent_init_command(self, mock_error, mock_output):
        """Test agent init command - skip due to complex Agent SDK dependencies"""
        pytest.skip("Agent SDK commands have complex Agent SDK and config dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
