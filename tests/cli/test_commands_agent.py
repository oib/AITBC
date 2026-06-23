"""
Agent Commands Tests
Tests for agent CLI commands
"""

import json
from unittest.mock import AsyncMock, patch

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

    @patch("aitbc_cli.commands.agent.output")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_train_command(self, mock_error, mock_output):
        """Test agent train command - skip due to complex subprocess dependencies"""
        pytest.skip("Agent commands have complex subprocess and config dependencies")

    def test_agent_ping_command_exists(self):
        """Test that agent ping subcommand is registered"""
        assert "ping" in agent.commands

    @patch("aitbc_cli.commands.agent.websockets")
    @patch("aitbc_cli.commands.agent.get_config")
    @patch("aitbc_cli.commands.agent.success")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_ping_sends_ping_and_gets_pong(self, mock_error, mock_success, mock_config, mock_ws):
        """Test agent ping: consume connection_established, send PING, receive PONG."""
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
            agent,
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

    @patch("aitbc_cli.commands.agent.websockets")
    @patch("aitbc_cli.commands.agent.get_config")
    @patch("aitbc_cli.commands.agent.success")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_ping_times_out_without_pong(self, mock_error, mock_success, mock_config, mock_ws):
        """Test agent ping reports timeout when no PONG arrives after connection."""
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
            agent,
            ["ping", "--agent", "hub-coordinator", "--sender", "follower", "--timeout", "1"],
        )

        assert result.exit_code == 0, result.output
        mock_error.assert_called_once()
        assert "No PONG" in mock_error.call_args[0][0]

    @patch("aitbc_cli.commands.agent.websockets")
    @patch("aitbc_cli.commands.agent.get_config")
    @patch("aitbc_cli.commands.agent.success")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_ping_connection_failure(self, mock_error, mock_success, mock_config, mock_ws):
        """Test agent ping reports error when WebSocket connection fails."""
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"

        from websockets.exceptions import WebSocketException

        mock_ws.connect.side_effect = WebSocketException("Connection refused")

        runner = CliRunner()
        result = runner.invoke(
            agent,
            ["ping", "--agent", "hub-coordinator", "--sender", "follower", "--timeout", "5"],
        )

        assert result.exit_code == 0, result.output
        mock_error.assert_called_once()
        assert "WebSocket error" in mock_error.call_args[0][0]

    def test_agent_request_coins_command_exists(self):
        """Test that agent request-coins subcommand is registered"""
        assert "request-coins" in agent.commands

    @patch("aitbc_cli.commands.agent._resolve_wallet_address")
    @patch("aitbc_cli.commands.agent.websockets")
    @patch("aitbc_cli.commands.agent.get_config")
    @patch("aitbc_cli.commands.agent.success")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_request_coins_auto_transfer(
        self, mock_error, mock_success, mock_config, mock_ws, mock_wallet
    ):
        """Test request-coins sends REQUEST_COINS and receives COINS_TRANSFERRED."""
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"
        mock_wallet.return_value = "aitbc1abc123"

        ws_conn = AsyncMock()
        ws_conn.send = AsyncMock()
        ws_conn.recv = AsyncMock(
            side_effect=[
                json.dumps({"type": "connection_established"}),
                json.dumps({
                    "type": "COINS_TRANSFERRED",
                    "sender": "hub-coordinator",
                    "recipient": "follower",
                    "amount": 100,
                    "wallet_address": "aitbc1abc123",
                    "transaction_hash": "0xabc123",
                    "timestamp": "2026-06-22T10:00:00Z",
                }),
            ]
        )
        ws_ctx = AsyncMock()
        ws_ctx.__aenter__ = AsyncMock(return_value=ws_conn)
        ws_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ws.connect.return_value = ws_ctx

        runner = CliRunner()
        result = runner.invoke(
            agent,
            ["request-coins", "--sender", "follower", "--timeout", "5"],
        )

        assert result.exit_code == 0, result.output
        ws_conn.send.assert_called_once()
        sent_frame = json.loads(ws_conn.send.call_args[0][0])
        assert "REQUEST_COINS" in sent_frame["payload"]["content"]
        assert "aitbc1abc123" in sent_frame["payload"]["content"]
        assert sent_frame["payload"]["recipient_id"] == "hub-coordinator"
        mock_success.assert_any_call("Received 100 AIT!")
        mock_error.assert_not_called()

    @patch("aitbc_cli.commands.agent._resolve_wallet_address")
    @patch("aitbc_cli.commands.agent.websockets")
    @patch("aitbc_cli.commands.agent.get_config")
    @patch("aitbc_cli.commands.agent.success")
    @patch("aitbc_cli.commands.agent.error")
    def test_agent_request_coins_pending_approval(
        self, mock_error, mock_success, mock_config, mock_ws, mock_wallet
    ):
        """Test request-coins handles pending_approval for subsequent requests."""
        mock_config.return_value.agent_coordinator_url = "http://hub:8107"
        mock_wallet.return_value = "aitbc1abc123"

        ws_conn = AsyncMock()
        ws_conn.send = AsyncMock()
        # pending_approval comes inside handler_acknowledgment
        ws_conn.recv = AsyncMock(
            side_effect=[
                json.dumps({"type": "connection_established"}),
                json.dumps({
                    "type": "handler_acknowledgment",
                    "handler_results": {
                        "message_type": "REQUEST_COINS",
                        "handlers_triggered": 1,
                        "results": [{
                            "handler": "request_coins_handler",
                            "result": {
                                "action": "coin_request_received",
                                "request_id": "req-follower-1234567890",
                                "status": "pending_approval",
                                "message": "Initial coins already granted. Further requests require manual approval. Use 'aitbc coin-requests approve <request_id>' to approve.",
                            },
                            "success": True,
                        }],
                    },
                }),
            ]
        )
        ws_ctx = AsyncMock()
        ws_ctx.__aenter__ = AsyncMock(return_value=ws_conn)
        ws_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ws.connect.return_value = ws_ctx

        runner = CliRunner()
        result = runner.invoke(
            agent,
            ["request-coins", "--sender", "follower", "--timeout", "5"],
        )

        assert result.exit_code == 0, result.output
        mock_success.assert_any_call("Request submitted — pending manual approval")
        mock_error.assert_not_called()

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
