"""Tests for the unified CLI surface (G8).

With the --show-deprecated gate removed, canonical top-level groups must appear
in the help output. Legacy `operations` and its subgroups are hidden and
emitted as deprecated, but still invocable for backward compatibility.
"""

from __future__ import annotations

from click.testing import CliRunner

from aitbc_cli.core.main import cli


def test_default_help_lists_canonical_groups():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ai" in result.output
    assert "market" in result.output
    assert "governance" in result.output
    # Legacy `operations` and its subgroups are hidden from default help.
    assert "  operations  " not in result.output
    assert "Deprecated commands are hidden" not in result.output
    assert "--show-deprecated" not in result.output


def test_canonical_market_group_runs():
    runner = CliRunner()
    result = runner.invoke(cli, ["market", "--help"])
    assert result.exit_code == 0
    assert "GPU and software" in result.output


def test_canonical_governance_group_runs():
    runner = CliRunner()
    result = runner.invoke(cli, ["governance", "--help"])
    assert result.exit_code == 0
    assert "governance" in result.output.lower()


def test_legacy_operations_group_is_hidden_and_deprecated():
    runner = CliRunner()
    result = runner.invoke(cli, ["operations", "--help"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower()


def test_legacy_operations_governance_subgroup_is_deprecated():
    runner = CliRunner()
    result = runner.invoke(cli, ["operations", "governance", "--help"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower()


def test_version_command_still_works():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "aitbc, version" in result.output
