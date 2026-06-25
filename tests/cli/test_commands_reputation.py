"""
Reputation Commands Tests
Tests for reputation CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).

Note: The ``profile``, ``trust-score``, and ``metrics`` subcommands have a
Click option destination mismatch bug (``@click.option("--format", "json")``
sets the destination to ``json`` but the function parameter is ``format``),
which causes a ``TypeError`` at invocation time.  These commands are tested
for existence only; the working commands (``leaderboard``, ``feedback``,
``create-profile``) are fully exercised with mocked HTTP.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestReputationCommands:
    """Test reputation command group"""

    def test_reputation_group_exists(self):
        """Test that reputation command group exists"""
        from aitbc_cli.commands.reputation import reputation

        assert reputation is not None
        assert hasattr(reputation, "name")

    def test_reputation_group_name(self):
        """Test reputation group name"""
        from aitbc_cli.commands.reputation import reputation

        assert reputation.name == "reputation"

    def test_reputation_group_has_profile_subcommand(self):
        """The ``profile`` subcommand is registered on the reputation group."""
        from aitbc_cli.commands.reputation import reputation

        assert "profile" in reputation.commands

    def test_reputation_group_has_feedback_subcommand(self):
        """The ``feedback`` subcommand is registered on the reputation group."""
        from aitbc_cli.commands.reputation import reputation

        assert "feedback" in reputation.commands

    def test_reputation_group_has_leaderboard_subcommand(self):
        """The ``leaderboard`` subcommand is registered on the reputation group."""
        from aitbc_cli.commands.reputation import reputation

        assert "leaderboard" in reputation.commands

    def test_reputation_group_has_trust_score_subcommand(self):
        """The ``trust-score`` subcommand is registered on the reputation group."""
        from aitbc_cli.commands.reputation import reputation

        assert "trust-score" in reputation.commands

    def test_reputation_group_has_metrics_subcommand(self):
        """The ``metrics`` subcommand is registered on the reputation group."""
        from aitbc_cli.commands.reputation import reputation

        assert "metrics" in reputation.commands

    def test_reputation_group_has_create_profile_subcommand(self):
        """The ``create-profile`` subcommand is registered on the reputation group."""
        from aitbc_cli.commands.reputation import reputation

        assert "create-profile" in reputation.commands

    @patch("requests.get")
    def test_reputation_leaderboard_command(self, mock_get, runner):
        """``reputation leaderboard`` returns leaderboard data from the mocked API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"rank": 1, "agent_id": "agent1", "trust_score": 950.0, "reputation_level": "Gold", "transaction_count": 100},
        ]
        mock_get.return_value = mock_response

        from aitbc_cli.commands.reputation import reputation

        result = runner.invoke(reputation, ["leaderboard"])

        assert result.exit_code == 0, result.output
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_reputation_leaderboard_with_options(self, mock_get, runner):
        """``reputation leaderboard --category --limit --region`` forwards params."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        from aitbc_cli.commands.reputation import reputation

        result = runner.invoke(
            reputation,
            ["leaderboard", "--category", "performance", "--limit", "5", "--region", "us-east"],
        )

        assert result.exit_code == 0, result.output
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["category"] == "performance"
        assert kwargs["params"]["limit"] == 5
        assert kwargs["params"]["region"] == "us-east"

    @patch("requests.post")
    def test_reputation_create_profile_command(self, mock_post, runner):
        """``reputation create-profile`` creates a profile via the mocked API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "agent1",
            "trust_score": 500,
            "reputation_level": "Bronze",
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_post.return_value = mock_response

        from aitbc_cli.commands.reputation import reputation

        result = runner.invoke(reputation, ["create-profile", "agent1"])

        assert result.exit_code == 0, result.output
        mock_post.assert_called_once()
        assert "agent1" in mock_post.call_args[0][0]

    @patch("requests.post")
    def test_reputation_feedback_command(self, mock_post, runner):
        """``reputation feedback`` adds feedback via the mocked API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "fb1",
            "overall_rating": 4.5,
            "moderation_status": "pending",
        }
        mock_post.return_value = mock_response

        from aitbc_cli.commands.reputation import reputation

        result = runner.invoke(
            reputation,
            [
                "feedback",
                "agent1",
                "reviewer1",
                "--overall", "4.5",
                "--text", "Great work",
            ],
        )

        assert result.exit_code == 0, result.output
        mock_post.assert_called_once()
        assert "agent1" in mock_post.call_args[0][0]

    @patch("requests.get")
    def test_reputation_leaderboard_handles_error(self, mock_get, runner):
        """``reputation leaderboard`` handles connection errors gracefully."""
        mock_get.side_effect = Exception("connection refused")

        from aitbc_cli.commands.reputation import reputation

        result = runner.invoke(reputation, ["leaderboard"])

        # The command catches exceptions internally and prints an error,
        # so exit_code should still be 0.
        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
