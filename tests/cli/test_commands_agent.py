"""
Agent Commands Tests
Tests for agent CLI commands
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.agent import agent


class TestAgentCommands:
    """Test agent command group"""

    def test_agent_group_exists(self):
        """Test that agent command group exists"""
        assert agent is not None
        assert hasattr(agent, "name")

    def test_agent_group_name(self):
        """Test agent group name"""
        assert agent.name == "agent"

    @patch("aitbc_cli.commands.agent.AITBCHTTPClient")
    @patch("aitbc_cli.commands.agent.get_config")
    @patch("aitbc_cli.commands.agent.success")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_send_command(self, mock_error, mock_success, mock_config, mock_http_class):
        """Test agent send command — sends a message via the Agent Coordinator.

        The original ``train`` subcommand was never implemented; ``send`` is the
        closest HTTP-based subcommand on the ``agent`` group.
        """
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "sent", "message_id": "msg-001"}

        runner = CliRunner()
        result = runner.invoke(
            agent,
            ["send", "hello world", "--to-agent", "hub-coordinator"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        # Verify the endpoint and payload
        call_args = mock_client.post.call_args
        assert "/api/v1/agent/messages/send" in call_args[0][0]
        assert call_args[1]["json"]["message"] == "hello world"
        assert call_args[1]["json"]["to_agent"] == "hub-coordinator"
        mock_success.assert_any_call("Message sent via Agent Coordinator")
        mock_error.assert_not_called()

    def test_agent_ping_command_exists(self):
        """Test that agent ping subcommand is registered"""
        assert "ping" in agent.commands

    def test_agent_request_coins_command_exists(self):
        """Test that agent request-coins subcommand is registered"""
        assert "request-coins" in agent.commands

    @patch("aitbc_cli.commands.agent._resolve_wallet_address")
    @patch("aitbc_cli.commands.agent.websockets")
    @patch("aitbc_cli.commands.agent.get_config")
    def test_agent_request_coins_no_wallet(self, mock_config, mock_ws, mock_wallet):
        """Test request-coins exits cleanly when no wallet is found."""
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"
        mock_wallet.return_value = None

        runner = CliRunner()
        result = runner.invoke(
            agent,
            ["request-coins", "--sender", "follower"],
        )

        assert result.exit_code == 0, result.output
        # WebSocket should not be called since wallet resolution failed
        mock_ws.connect.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
