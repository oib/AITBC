"""
System Architect Commands Tests
Tests for system architect CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest


class TestSystemArchitectCommands:
    """Test system architect command group"""

    def test_system_architect_group_exists(self):
        """Test that system_architect command group exists"""
        from aitbc_cli.commands.system_architect import system_architect

        assert system_architect is not None
        assert hasattr(system_architect, "name")

    def test_system_architect_group_name(self):
        """Test system_architect group name"""
        from aitbc_cli.commands.system_architect import system_architect

        assert system_architect.name == "system-architect"

    def test_system_architect_group_has_audit_subcommand(self):
        """The ``audit`` subcommand is registered on the system_architect group."""
        from aitbc_cli.commands.system_architect import system_architect

        assert "audit" in system_architect.commands

    def test_system_architect_group_has_paths_subcommand(self):
        """The ``paths`` subcommand is registered on the system_architect group."""
        from aitbc_cli.commands.system_architect import system_architect

        assert "paths" in system_architect.commands

    def test_system_architect_group_has_check_subcommand(self):
        """The ``check`` subcommand is registered on the system_architect group."""
        from aitbc_cli.commands.system_architect import system_architect

        assert "check" in system_architect.commands

    def test_system_architect_audit_command(self, runner):
        """``system-architect audit`` outputs the architecture audit report."""
        from aitbc_cli.commands.system_architect import system_architect

        result = runner.invoke(system_architect, ["audit"])

        assert result.exit_code == 0, result.output
        assert "System Architecture Audit" in result.output

    def test_system_architect_paths_command(self, runner):
        """``system-architect paths`` outputs the architecture paths."""
        from aitbc_cli.commands.system_architect import system_architect

        result = runner.invoke(system_architect, ["paths"])

        assert result.exit_code == 0, result.output
        assert "System Architecture Paths" in result.output

    def test_system_architect_check_command(self, runner):
        """``system-architect check`` checks service configuration."""
        from aitbc_cli.commands.system_architect import system_architect

        result = runner.invoke(system_architect, ["check"])

        assert result.exit_code == 0, result.output
        assert "Service Check" in result.output

    def test_system_architect_check_with_service(self, runner):
        """``system-architect check --service`` checks a specific service."""
        from aitbc_cli.commands.system_architect import system_architect

        result = runner.invoke(system_architect, ["check", "--service", "blockchain-node"])

        assert result.exit_code == 0, result.output
        assert "blockchain-node" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
