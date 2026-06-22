"""
AI CLI Tests
Tests for AI job management CLI commands
"""


import pytest
from aitbc_cli.commands.ai import ai
from click.testing import CliRunner


class TestAICLI:
    """Test AI job management CLI commands"""

    def test_ai_group(self):
        """Test AI command group exists"""
        runner = CliRunner()
        result = runner.invoke(ai, ["--help"])
        assert result.exit_code == 0
        assert "AI job submission and inspection" in result.output

    def test_ai_submit_command(self):
        """Test AI submit command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["submit", "--help"])
        assert result.exit_code == 0
        assert "Submit an AI job" in result.output

    def test_ai_jobs_command(self):
        """Test AI jobs command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["jobs", "--help"])
        assert result.exit_code == 0
        assert "List AI jobs" in result.output

    def test_ai_status_command(self):
        """Test AI status command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["status", "--help"])
        assert result.exit_code == 0
        assert "Show AI job status" in result.output

    def test_ai_service_list_command(self):
        """Test AI service list command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["service", "list", "--help"])
        assert result.exit_code == 0
        assert "List available AI services" in result.output

    def test_ai_service_status_command(self):
        """Test AI service status command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["service", "service-status", "--help"])
        assert result.exit_code == 0
        assert "Check AI service status" in result.output

    def test_ai_service_test_command(self):
        """Test AI service test command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["service", "test", "--help"])
        assert result.exit_code == 0
        assert "Test AI service endpoint" in result.output

    def test_ai_results_command(self):
        """Test AI results command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["results", "--help"])
        assert result.exit_code == 0
        assert "Show AI job results" in result.output

    def test_ai_cancel_command(self):
        """Test AI cancel command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["cancel", "--help"])
        assert result.exit_code == 0
        assert "Cancel AI job" in result.output

    def test_ai_stats_command(self):
        """Test AI stats command"""
        runner = CliRunner()
        result = runner.invoke(ai, ["stats", "--help"])
        assert result.exit_code == 0
        assert "AI service statistics" in result.output

    def test_ai_service_group(self):
        """Test AI service command group"""
        runner = CliRunner()
        result = runner.invoke(ai, ["service", "--help"])
        assert result.exit_code == 0
        assert "AI service management" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
