"""
Hermes Commands Tests
Tests for hermes CLI commands
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.hermes import hermes


class TestHermesCommands:
    """Test hermes command group"""

    def test_hermes_group_exists(self):
        """Test that hermes command group exists"""
        assert hermes is not None
        assert hasattr(hermes, "name")

    def test_hermes_group_name(self):
        """Test hermes group name"""
        assert hermes.name == "hermes"

    @patch("aitbc_cli.commands.hermes.output")
    @patch("aitbc_cli.commands.hermes.error")
    def test_hermes_train_command(self, mock_error, mock_output):
        """Test hermes train command - skip due to complex subprocess dependencies"""
        pytest.skip("Hermes commands have complex subprocess and config dependencies")

    def test_hermes_ping_command_exists(self):
        """Test that hermes ping subcommand is registered"""
        assert "ping" in hermes.commands

    @patch("aitbc_cli.commands.hermes.websockets")
    @patch("aitbc_cli.commands.hermes.get_config")
    @patch("aitbc_cli.commands.hermes.success")
    @patch("aitbc_cli.commands.hermes.error")
    def test_hermes_ping_sends_ping_and_gets_pong(self, mock_error, mock_success, mock_config, mock_ws):
        """Test hermes ping: consume connection_established, send PING, receive PONG."""
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"

        # Simulate WebSocket message order:
        # 1. connection_established (on connect)
        # 2. PONG (from ping_handler)
        # 3. handler_acknowledgment (after trigger_handlers)
        ws_conn = AsyncMock()
        ws_conn.send = AsyncMock()
        ws_conn.recv = AsyncMock(
            side_effect=[
                json.dumps({"type": "connection_established", "agent_id": "follower"}),
                json.dumps({
                    "type": "PONG",
                    "sender": "hub-coordinator",
                    "recipient": "follower",
                    "content": "PONG from hub-coordinator",
                    "timestamp": "2026-06-22T00:00:00Z",
                }),
            ]
        )
        ws_ctx = AsyncMock()
        ws_ctx.__aenter__ = AsyncMock(return_value=ws_conn)
        ws_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ws.connect.return_value = ws_ctx

        runner = CliRunner()
        result = runner.invoke(
            hermes,
            ["ping", "--agent", "hub-coordinator", "--sender", "follower", "--timeout", "5"],
        )

        assert result.exit_code == 0, result.output
        # Verify PING frame was sent
        ws_conn.send.assert_called_once()
        sent_frame = json.loads(ws_conn.send.call_args[0][0])
        assert sent_frame["type"] == "message"
        assert sent_frame["payload"]["content"] == "PING"
        assert sent_frame["payload"]["recipient_id"] == "hub-coordinator"
        mock_success.assert_any_call("PONG received from hub-coordinator")
        mock_error.assert_not_called()

    @patch("aitbc_cli.commands.hermes.websockets")
    @patch("aitbc_cli.commands.hermes.get_config")
    @patch("aitbc_cli.commands.hermes.success")
    @patch("aitbc_cli.commands.hermes.error")
    def test_hermes_ping_times_out_without_pong(self, mock_error, mock_success, mock_config, mock_ws):
        """Test hermes ping reports timeout when no PONG arrives after connection."""
        import asyncio

        mock_config.return_value.agent_coordinator_url = "http://hub:8107"

        # connection_established arrives, then PING is sent, then recv times out
        ws_conn = AsyncMock()
        ws_conn.send = AsyncMock()
        ws_conn.recv = AsyncMock(
            side_effect=[
                json.dumps({"type": "connection_established"}),
                asyncio.TimeoutError(),
            ]
        )
        ws_ctx = AsyncMock()
        ws_ctx.__aenter__ = AsyncMock(return_value=ws_conn)
        ws_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ws.connect.return_value = ws_ctx

        runner = CliRunner()
        result = runner.invoke(
            hermes,
            ["ping", "--agent", "hub-coordinator", "--sender", "follower", "--timeout", "1"],
        )

        assert result.exit_code == 0, result.output
        mock_error.assert_called_once()
        assert "No PONG" in mock_error.call_args[0][0]

    @patch("aitbc_cli.commands.hermes.websockets")
    @patch("aitbc_cli.commands.hermes.get_config")
    @patch("aitbc_cli.commands.hermes.success")
    @patch("aitbc_cli.commands.hermes.error")
    def test_hermes_ping_connection_failure(self, mock_error, mock_success, mock_config, mock_ws):
        """Test hermes ping reports error when WebSocket connection fails."""
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"

        from websockets.exceptions import WebSocketException

        mock_ws.connect.side_effect = WebSocketException("Connection refused")

        runner = CliRunner()
        result = runner.invoke(
            hermes,
            ["ping", "--agent", "hub-coordinator", "--sender", "follower", "--timeout", "5"],
        )

        assert result.exit_code == 0, result.output
        mock_error.assert_called_once()
        assert "WebSocket error" in mock_error.call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
