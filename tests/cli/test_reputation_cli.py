"""
Reputation CLI Tests
Tests for reputation management CLI commands
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.reputation import reputation


class TestReputationCLI:
    """Test reputation CLI commands"""

    def test_reputation_group(self):
        """Test reputation command group exists"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['--help'])
        assert result.exit_code == 0
        assert 'Reputation management commands' in result.output

    def test_reputation_profile_command(self):
        """Test reputation profile command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['profile', '--help'])
        assert result.exit_code == 0
        assert 'Get reputation profile for an agent' in result.output

    def test_reputation_feedback_command(self):
        """Test reputation feedback command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['feedback', '--help'])
        assert result.exit_code == 0
        assert 'Add community feedback for an agent' in result.output

    def test_reputation_leaderboard_command(self):
        """Test reputation leaderboard command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['leaderboard', '--help'])
        assert result.exit_code == 0
        assert 'Get reputation leaderboard' in result.output

    def test_reputation_trust_score_command(self):
        """Test reputation trust-score command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['trust-score', '--help'])
        assert result.exit_code == 0
        assert 'Get detailed trust score breakdown for an agent' in result.output

    def test_reputation_metrics_command(self):
        """Test reputation metrics command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['metrics', '--help'])
        assert result.exit_code == 0
        assert 'Get overall reputation system metrics' in result.output

    def test_reputation_create_profile_command(self):
        """Test reputation create-profile command"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['create-profile', '--help'])
        assert result.exit_code == 0
        assert 'Create a new reputation profile for an agent' in result.output

    def test_reputation_profile_with_format_option(self):
        """Test reputation profile command with format option"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['profile', '--help'])
        assert result.exit_code == 0
        assert '--format' in result.output
        assert 'json' in result.output
        assert 'table' in result.output

    def test_reputation_feedback_with_rating_options(self):
        """Test reputation feedback command with rating options"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['feedback', '--help'])
        assert result.exit_code == 0
        assert '--overall' in result.output
        assert '--performance' in result.output
        assert '--communication' in result.output
        assert '--reliability' in result.output
        assert '--value' in result.output

    def test_reputation_leaderboard_with_options(self):
        """Test reputation leaderboard command with options"""
        runner = CliRunner()
        result = runner.invoke(reputation, ['leaderboard', '--help'])
        assert result.exit_code == 0
        assert '--category' in result.output
        assert '--limit' in result.output
        assert '--region' in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
