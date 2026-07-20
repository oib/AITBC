"""
CLI integration tests against a live (in-memory) coordinator.

Spins up the real coordinator FastAPI app with an in-memory SQLite DB,
then patches httpx.Client so every CLI command's HTTP call is routed
through the ASGI transport instead of making real network requests.

v0.5.17 B2: The coordinator-api auth structure was refactored — app.deps
no longer exists and APIKeyValidator was removed. This test file needs a
full rewrite against the new auth layer (app/auth/dependencies.py).
"""

from click.testing import CliRunner


def test_cli_help_exposes_current_command_surface():
    """The current CLI command group remains loadable without a live API."""
    from aitbc_cli.core.main import cli

    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    assert "bridge" in result.output
    assert "workflow" in result.output
    assert "resource" in result.output
