"""
Reputation CLI Tests
Tests for reputation management CLI commands
"""

import pytest
from unittest.mock import MagicMock, patch

from aitbc_cli.commands.reputation import reputation
from aitbc_cli.utils.http_client import NetworkError
from click.testing import CliRunner


class TestReputationCLI:
    """Test reputation CLI commands"""

    def test_reputation_group(self):
        """Test reputation command group exists"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["--help"])
        assert result.exit_code == 0
        assert "Manage and query agent reputation profiles" in result.output

    def test_reputation_profile_command(self):
        """Test reputation profile command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["profile", "--help"])
        assert result.exit_code == 0
        assert "Get the reputation profile for an agent" in result.output

    def test_reputation_feedback_command(self):
        """Test reputation feedback command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["feedback", "--help"])
        assert result.exit_code == 0
        assert "Add community feedback for an agent" in result.output

    def test_reputation_leaderboard_command(self):
        """Test reputation leaderboard command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["leaderboard", "--help"])
        assert result.exit_code == 0
        assert "Get the agent reputation leaderboard" in result.output

    def test_reputation_trust_score_command(self):
        """Test reputation trust-score command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["trust-score", "--help"])
        assert result.exit_code == 0
        assert "Get a detailed trust score breakdown for an agent" in result.output

    def test_reputation_metrics_command(self):
        """Test reputation metrics command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["metrics", "--help"])
        assert result.exit_code == 0
        assert "Get overall reputation system metrics" in result.output

    def test_reputation_create_profile_command(self):
        """Test reputation create-profile command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["create-profile", "--help"])
        assert result.exit_code == 0
        assert "Create a new reputation profile for an agent" in result.output

    def test_reputation_profile_with_format_option(self):
        """Test reputation profile command with format option"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["profile", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "json" in result.output
        assert "table" in result.output

    def test_reputation_feedback_with_rating_options(self):
        """Test reputation feedback command with rating options"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["feedback", "--help"])
        assert result.exit_code == 0
        assert "--overall" in result.output
        assert "--performance" in result.output
        assert "--communication" in result.output
        assert "--reliability" in result.output
        assert "--value" in result.output

    def test_reputation_leaderboard_with_options(self):
        """Test reputation leaderboard command with options"""
        runner = CliRunner()
        result = runner.invoke(reputation, ["leaderboard", "--help"])
        assert result.exit_code == 0
        assert "--category" in result.output
        assert "--limit" in result.output
        assert "--region" in result.output


class TestReputationFindings2210:
    """#2210: --job-id plumbing and honest HTTP-error labeling."""

    def test_feedback_sends_job_id_without_reviewer_id(self):
        runner = CliRunner()
        client = MagicMock()
        client.post.return_value = {"id": "fb_1", "overall_rating": 5.0}
        with patch("aitbc_cli.commands.reputation._coordinator_client", return_value=client):
            result = runner.invoke(
                reputation,
                ["feedback", "--agent-id", "agent-1", "--job-id", "job-9", "--overall", "5"],
            )

        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"]
        assert payload["job_id"] == "job-9"
        assert "reviewer_id" not in payload

    def test_profile_404_not_labeled_network_error(self):
        runner = CliRunner()
        response = MagicMock()
        response.status_code = 404
        response.json.return_value = {"detail": "Reputation profile not found"}
        cause = RuntimeError("Client error '404 Not Found'")
        cause.response = response
        err = NetworkError("wrapped")
        err.__cause__ = cause
        client = MagicMock()
        client.get.side_effect = err
        with patch("aitbc_cli.commands.reputation._coordinator_client", return_value=client):
            result = runner.invoke(reputation, ["profile", "--agent-id", "ghost"])

        assert result.exit_code != 0
        assert "Request failed (HTTP 404)" in result.output
        assert "Reputation profile not found" in result.output
        assert "Network error" not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
