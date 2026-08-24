"""Tests for the G8 CLI surface reduction."""

from __future__ import annotations

import sys

from click.testing import CliRunner

from aitbc_cli.core.main import cli


def test_default_help_hides_deprecated_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ai" in result.output
    assert "Deprecated commands are hidden" in result.output
    # The Commands section must not list the deprecated groups as first-class entries.
    commands_section = result.output.split("Commands:")[-1].split("\n\n")[0]
    command_names = {
        line.split()[0] for line in commands_section.splitlines() if line.strip() and not line.strip().startswith("-")
    }
    assert "marketplace" not in command_names
    assert "operations" not in command_names


def test_show_deprecated_env_reveals_deprecated_commands():
    runner = CliRunner(env={"AITBC_CLI_SHOW_DEPRECATED": "1"})
    result = runner.invoke(cli, ["marketplace", "--help"])
    assert result.exit_code == 0
    assert "Legacy global chain marketplace" in result.output


def test_show_deprecated_argv_reveals_deprecated_commands(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["aitbc", "--show-deprecated", "operations", "--help"])
    runner = CliRunner()
    result = runner.invoke(cli, ["--show-deprecated", "operations", "--help"])
    assert result.exit_code == 0
    assert "Legacy on-chain operations" in result.output


def test_deprecated_command_fails_without_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["marketplace"])
    assert result.exit_code != 0
    assert "deprecated" in result.output
    assert "--show-deprecated" in result.output


def test_validated_command_available_without_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "aitbc, version" in result.output


def test_deprecated_command_help_runs_with_env():
    runner = CliRunner(env={"AITBC_CLI_SHOW_DEPRECATED": "1"})
    result = runner.invoke(cli, ["marketplace", "--help"])
    assert result.exit_code == 0
    assert "Legacy global chain marketplace" in result.output


def test_deprecated_command_help_runs_with_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["aitbc", "--show-deprecated", "marketplace", "--help"])
    runner = CliRunner()
    result = runner.invoke(cli, ["--show-deprecated", "marketplace", "--help"])
    assert result.exit_code == 0
    assert "Legacy global chain marketplace" in result.output
