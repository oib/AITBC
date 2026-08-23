"""Tests for the G8 CLI surface reduction."""

from __future__ import annotations

import sys

import pytest
from click.testing import CliRunner

from aitbc_cli.core.main import cli


def test_default_help_hides_unvalidated_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ai" in result.output
    assert "analytics" not in result.output
    assert "Unvalidated commands are hidden" in result.output


def test_show_deprecated_env_reveals_all_commands():
    runner = CliRunner(env={"AITBC_CLI_SHOW_DEPRECATED": "1"})
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ai" in result.output
    assert "analytics" in result.output


def test_show_deprecated_argv_reveals_all_commands(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["aitbc", "--show-deprecated", "--help"])
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "analytics" in result.output


def test_deprecated_command_fails_without_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["analytics"])
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
    result = runner.invoke(cli, ["analytics", "--help"])
    assert result.exit_code == 0
    assert "Chain analytics" in result.output


def test_deprecated_command_help_runs_with_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["aitbc", "--show-deprecated", "analytics", "--help"])
    runner = CliRunner()
    result = runner.invoke(cli, ["--show-deprecated", "analytics", "--help"])
    assert result.exit_code == 0
    assert "Chain analytics" in result.output
