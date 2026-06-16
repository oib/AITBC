"""Tests for aitbc.training_setup.cli"""

from unittest.mock import patch

from aitbc.training_setup.cli import cli
from click.testing import CliRunner


class TestTrainingCLI:
    def test_cli_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "AITBC Training Environment" in result.output

    def test_setup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", "--help"])
        assert result.exit_code == 0
        assert "--aitbc-dir" in result.output

    def test_setup(self):
        runner = CliRunner()
        with patch("aitbc.training_setup.cli.TrainingEnvironment") as mock_env:
            mock_env.return_value.setup_full_environment.return_value = {"status": "ok"}
            result = runner.invoke(cli, ["setup"])
        assert result.exit_code == 0
        assert "Setup Summary" in result.output
