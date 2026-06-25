"""
Messaging Commands Tests
Tests for messaging CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestMessagingCommands:
    """Test messaging command group"""

    def test_messaging_group_exists(self):
        """Test that messaging command group exists"""
        from aitbc_cli.commands.messaging import messaging

        assert messaging is not None
        assert hasattr(messaging, "name")

    def test_messaging_group_name(self):
        """Test messaging group name"""
        from aitbc_cli.commands.messaging import messaging

        assert messaging.name == "messaging"

    def test_messaging_group_has_send_subcommand(self):
        """The ``send`` subcommand is registered on the messaging group."""
        from aitbc_cli.commands.messaging import messaging

        assert "send" in messaging.commands

    def test_messaging_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the messaging group."""
        from aitbc_cli.commands.messaging import messaging

        assert "list" in messaging.commands

    def test_messaging_group_has_topic_subcommand(self):
        """The ``topic`` subcommand is registered on the messaging group."""
        from aitbc_cli.commands.messaging import messaging

        assert "topic" in messaging.commands

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_messaging_send_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``messaging send`` sends a message via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "sent", "message_id": "test123"}

        from aitbc_cli.commands.messaging import messaging

        result = runner.invoke(
            messaging,
            ["send", "--recipient", "ait1qtestaddress0000000000000000000000000", "--message", "Hello"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert "/rpc/messaging/send" in args[0]
        assert kwargs["json"]["recipient"] == "ait1qtestaddress0000000000000000000000000"
        assert kwargs["json"]["message"] == "Hello"

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_messaging_send_falls_back_on_network_error(self, mock_http_class, runner):
        """``messaging send`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.messaging import messaging
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            messaging,
            ["send", "--recipient", "ait1qtestaddress0000000000000000000000000", "--message", "Hello"],
        )

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_messaging_list_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``messaging list`` lists messages from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"messages": []}

        from aitbc_cli.commands.messaging import messaging

        result = runner.invoke(messaging, ["list"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/messaging/list" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_messaging_list_falls_back_on_network_error(self, mock_http_class, runner):
        """``messaging list`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.messaging import messaging
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(messaging, ["list"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_messaging_topic_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``messaging topic`` creates a forum topic via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"topic_id": "topic123", "status": "created"}

        from aitbc_cli.commands.messaging import messaging

        result = runner.invoke(
            messaging,
            ["topic", "--title", "Test Topic", "--description", "Test Description"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert "/rpc/messaging/topic" in args[0]
        assert kwargs["json"]["title"] == "Test Topic"

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_messaging_topic_aborts_on_network_error(self, mock_http_class, runner):
        """``messaging topic`` aborts on NetworkError (no fallback)."""
        from aitbc_cli.commands.messaging import messaging
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            messaging,
            ["topic", "--title", "Test Topic", "--description", "Test Description"],
        )

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
