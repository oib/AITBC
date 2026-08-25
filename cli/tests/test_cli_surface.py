"""Tests for the unified CLI surface (G8).

With the --show-deprecated gate removed, all top-level groups must appear in the
help output and be invocable without a flag.
"""

from __future__ import annotations

from click.testing import CliRunner

from aitbc_cli.core.main import cli


def test_default_help_lists_all_groups():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ai" in result.output
    # Legacy groups are no longer hidden.
    assert "marketplace" in result.output
    assert "operations" in result.output
    assert "Deprecated commands are hidden" not in result.output


def test_legacy_marketplace_group_runs_without_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["marketplace", "--help"])
    # It may still fail for other reasons, but it must not be blocked as deprecated.
    assert "deprecated" not in result.output.lower() or result.exit_code == 0
    assert "--show-deprecated" not in result.output


def test_legacy_operations_group_runs_without_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["operations", "--help"])
    assert "deprecated" not in result.output.lower() or result.exit_code == 0
    assert "--show-deprecated" not in result.output


def test_version_command_still_works():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "aitbc, version" in result.output
