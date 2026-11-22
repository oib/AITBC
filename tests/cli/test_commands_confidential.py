"""Tests for the confidential CLI commands.

These verify that ``confidential send`` falls back to a simulated local
settlement when the coordinator reports that confidential TEE is unavailable.
"""

from unittest.mock import MagicMock, patch

from aitbc.exceptions import NetworkError


def _http_error(message: str, status_code: int) -> NetworkError:
    """NetworkError shaped like the real client's wrap of a requests.HTTPError.

    ``AITBCHTTPClient`` raises ``NetworkError(...) from http_error`` and the
    status classifier walks the cause chain for ``.response.status_code`` —
    a bare message string carries no response and must NOT classify.
    """
    err = NetworkError(message)
    cause = Exception(f"{status_code} Error")
    cause.response = MagicMock(status_code=status_code)
    err.__cause__ = cause
    return err


class TestConfidentialCommands:
    """Test confidential command group"""

    def test_confidential_send_falls_back_on_tee_disabled(self, runner):
        """``confidential send`` uses the local simulated result when the coordinator returns 503."""
        from aitbc_cli.commands.confidential import confidential

        mock_client = MagicMock()
        mock_client.post.side_effect = _http_error(
            "POST request failed: Retry attempts exhausted: 503 Server Error: Service Unavailable for url: /v1/confidential/payments",
            503,
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

    def test_confidential_send_falls_back_on_unserved_route(self, runner):
        """``confidential send`` uses simulated settlement when the coordinator 404s the route (#2425)."""
        from aitbc_cli.commands.confidential import confidential

        mock_client = MagicMock()
        mock_client.post.side_effect = _http_error(
            "POST request failed: 404 Client Error: Not Found for url: /c/v1/confidential/payments",
            404,
        )

        with patch("aitbc_cli.commands.confidential._api_client", return_value=mock_client):
            result = runner.invoke(
                confidential,
                ["send", "--wallet-id", "wallet-1", "--recipient-id", "recipient-1", "--amount", "10"],
            )

        assert result.exit_code == 0, result.output
        assert "does not serve /v1/confidential/payments" in result.output
        assert "simulated" in result.output
        assert mock_client.post.call_count == 1

    def test_confidential_send_still_aborts_on_other_errors(self, runner):
        """Non-404/503 coordinator errors still abort — no blanket fallback."""
        from aitbc_cli.commands.confidential import confidential

        mock_client = MagicMock()
        mock_client.post.side_effect = _http_error(
            "POST request failed: 500 Server Error for url: /v1/confidential/payments",
            500,
        )

        with patch("aitbc_cli.commands.confidential._api_client", return_value=mock_client):
            result = runner.invoke(
                confidential,
                ["send", "--wallet-id", "wallet-1", "--recipient-id", "recipient-1", "--amount", "10"],
            )

        assert result.exit_code != 0
        assert "simulated" not in result.output

    def test_confidential_send_aborts_on_unreachable_with_status_digits(self, runner):
        """#2478: a transport failure whose text contains '404'/'503' (URL port,
        hash) but carries NO response must not take the simulated fallback —
        only a real HTTP status classifies."""
        from aitbc_cli.commands.confidential import confidential

        mock_client = MagicMock()
        mock_client.post.side_effect = NetworkError(
            "POST request failed: Connection refused for url: http://coordinator:8404/v1/confidential/payments "
            "(see tx 0xdeadbeef40450403)"
        )

        with patch("aitbc_cli.commands.confidential._api_client", return_value=mock_client):
            result = runner.invoke(
                confidential,
                ["send", "--wallet-id", "wallet-1", "--recipient-id", "recipient-1", "--amount", "10"],
            )

        assert result.exit_code != 0
        assert "simulated" not in result.output
        assert "settled" not in result.output

    def test_confidential_send_group_and_command_exist(self, runner):
        """The confidential command group and its send subcommand are registered."""
        from aitbc_cli.commands.confidential import confidential

        assert confidential is not None
        assert "send" in confidential.commands
