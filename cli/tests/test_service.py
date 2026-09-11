"""Unit tests for the aitbc service command group."""

from __future__ import annotations

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_service_group_registered_in_cli(runner):
    """`aitbc service --help` must list the harden subcommand."""
    from aitbc_cli.core.main import cli

    result = runner.invoke(cli, ["service", "--help"])
    assert result.exit_code == 0, result.output
    assert "harden" in result.output


def test_service_harden_requires_service_or_all(runner):
    """`service harden` must require --service or --all."""
    from aitbc_cli.core.main import cli

    result = runner.invoke(cli, ["service", "harden"])
    assert result.exit_code != 0
    assert "Specify --service" in (result.output + str(result.exception))


def test_service_harden_updates_unit_file(runner, tmp_path):
    """`service harden --service` applies the sandbox directives and preserves ReadWritePaths."""
    from aitbc_cli.core.main import cli

    unit = tmp_path / "aitbc-test.service"
    unit.write_text(
        "[Unit]\nDescription=test\n\n[Service]\nType=simple\nExecStart=/usr/bin/python test.py\nProtectSystem=no\n"
    )

    result = runner.invoke(
        cli,
        ["service", "harden", "--service", str(unit), "--no-restart"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0, result.output
    updated = unit.read_text()
    assert "ProtectSystem=full" in updated
    assert "ProtectHome=read-only" in updated
    assert "MemoryDenyWriteExecute=no" in updated
    assert "ReadWritePaths=/var/lib/aitbc /var/log/aitbc /run/aitbc" in updated


def test_service_harden_preserves_existing_read_write_paths(runner, tmp_path):
    """Existing ReadWritePaths are not overwritten."""
    from aitbc_cli.core.main import cli

    unit = tmp_path / "aitbc-test.service"
    unit.write_text(
        "[Unit]\n"
        "Description=test\n\n"
        "[Service]\n"
        "ExecStart=/usr/bin/python test.py\n"
        "ReadWritePaths=/var/lib/aitbc/test /var/log/aitbc\n"
    )

    result = runner.invoke(
        cli,
        ["service", "harden", "--service", str(unit), "--no-restart"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0, result.output
    updated = unit.read_text()
    assert "ReadWritePaths=/var/lib/aitbc/test /var/log/aitbc" in updated


def test_service_harden_rejects_missing_section(runner, tmp_path):
    """A unit without [Service] is reported as unchanged."""
    from aitbc_cli.core.main import cli

    unit = tmp_path / "aitbc-test.service"
    unit.write_text("[Unit]\nDescription=test\n")

    result = runner.invoke(
        cli,
        ["service", "harden", "--service", str(unit), "--no-restart"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0, result.output
    assert "no [Service] section" in result.output
