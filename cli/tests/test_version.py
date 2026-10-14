#!/usr/bin/env python3
"""User-facing version output must report the aitbc_cli package version.

`aitbc version` and `aitbc --version` used to print a hardcoded string in
aitbc_cli.core.main that drifted from aitbc_cli.__version__.
"""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestVersionOutput:
    """The version users see is the canonical package version."""

    def test_main_module_does_not_shadow_package_version(self):
        import aitbc_cli
        from aitbc_cli.core import main

        assert main.__version__ == aitbc_cli.__version__

    def test_version_flag_matches_package(self, runner):
        # --version is an eager option: output and exit before the group
        # callback runs, so this never touches config or chain-id detection.
        import aitbc_cli
        from aitbc_cli.core.main import cli

        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert result.output.strip() == f"aitbc, version {aitbc_cli.__version__}"

    def test_version_command_matches_package(self, runner):
        # Invoked standalone so the group callback (config load, chain-id
        # probe) never runs — the command itself needs no context.
        import aitbc_cli
        from aitbc_cli.core.main import version

        result = runner.invoke(version)
        assert result.exit_code == 0
        assert f"aitbc, version {aitbc_cli.__version__}" in result.output
