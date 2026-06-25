"""
Coin Requests Commands Tests
Tests for coin_requests CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCoinRequestsCommands:
    """Test coin_requests command group"""

    def test_coin_requests_group_exists(self):
        """Test that coin_requests command group exists"""
        from aitbc_cli.commands.coin_requests import coin_requests

        assert coin_requests is not None
        assert hasattr(coin_requests, "name")

    def test_coin_requests_group_name(self):
        """Test coin_requests group name"""
        from aitbc_cli.commands.coin_requests import coin_requests

        assert coin_requests.name == "coin-requests"

    def test_coin_requests_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the coin_requests group."""
        from aitbc_cli.commands.coin_requests import coin_requests

        assert "list" in coin_requests.commands

    def test_coin_requests_group_has_approve_subcommand(self):
        """The ``approve`` subcommand is registered on the coin_requests group."""
        from aitbc_cli.commands.coin_requests import coin_requests

        assert "approve" in coin_requests.commands

    @patch("aitbc_cli.commands.coin_requests.init_db")
    @patch("aitbc_cli.commands.coin_requests.get_db_session")
    def test_coin_requests_list_command(
        self, mock_get_db_session, mock_init_db, runner
    ):
        """``coin_requests list`` shows 'No coin requests found' when DB is empty."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.order_by.return_value.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_get_db_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_db_session.return_value.__exit__ = MagicMock(return_value=None)

        from aitbc_cli.commands.coin_requests import coin_requests

        result = runner.invoke(coin_requests, ["list"])

        assert result.exit_code == 0, result.output
        assert "No coin requests found" in result.output

    @patch("aitbc_cli.commands.coin_requests.init_db")
    @patch("aitbc_cli.commands.coin_requests.get_db_session")
    def test_coin_requests_show_not_found(
        self, mock_get_db_session, mock_init_db, runner
    ):
        """``coin_requests show`` reports 'not found' for a non-existent request."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_get_db_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_db_session.return_value.__exit__ = MagicMock(return_value=None)

        from aitbc_cli.commands.coin_requests import coin_requests

        result = runner.invoke(coin_requests, ["show", "nonexistent-req-id"])

        assert result.exit_code == 0, result.output
        assert "not found" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
