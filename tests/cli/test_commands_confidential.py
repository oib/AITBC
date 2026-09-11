"""Tests for the confidential CLI commands.

These verify that ``confidential send`` falls back to a simulated local
settlement when the coordinator reports that confidential TEE is unavailable.
"""

from unittest.mock import MagicMock, patch

from aitbc.exceptions import NetworkError


class TestConfidentialCommands:
    """Test confidential command group"""

    def test_confidential_send_falls_back_on_tee_disabled(self, runner):
        """``confidential send`` uses the local simulated result when the coordinator returns 503."""
        from aitbc_cli.commands.confidential import confidential

        mock_client = MagicMock()
        mock_client.post.side_effect = NetworkError(
            "POST request failed: Retry attempts exhausted: 503 Server Error: Service Unavailable for url: /v1/confidential/payments"
        )

        with patch("aitbc_cli.commands.confidential._api_client", return_value=mock_client):
            result = runner.invoke(
                confidential,
                ["send", "--wallet-id", "wallet-1", "--recipient-id", "recipient-1", "--amount", "10"],
            )

        assert result.exit_code == 0, result.output
        assert "settled" in result.output
        assert "simulated" in result.output
        assert mock_client.post.call_count == 1

    def test_confidential_send_group_and_command_exist(self, runner):
        """The confidential command group and its send subcommand are registered."""
        from aitbc_cli.commands.confidential import confidential

        assert confidential is not None
        assert "send" in confidential.commands
