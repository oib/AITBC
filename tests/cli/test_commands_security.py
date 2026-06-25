"""
Security Commands Tests
Tests for security CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest


class TestSecurityCommands:
    """Test security command group"""

    def test_security_group_exists(self):
        """Test that security command group exists"""
        from aitbc_cli.commands.security import security

        assert security is not None
        assert hasattr(security, "name")

    def test_security_group_name(self):
        """Test security group name"""
        from aitbc_cli.commands.security import security

        assert security.name == "security"

    def test_security_group_has_audit_subcommand(self):
        """The ``audit`` subcommand is registered on the security group."""
        from aitbc_cli.commands.security import security

        assert "audit" in security.commands

    def test_security_group_has_scan_subcommand(self):
        """The ``scan`` subcommand is registered on the security group."""
        from aitbc_cli.commands.security import security

        assert "scan" in security.commands

    def test_security_group_has_patch_subcommand(self):
        """The ``patch`` subcommand is registered on the security group."""
        from aitbc_cli.commands.security import security

        assert "patch" in security.commands

    def test_security_audit_command(self, runner):
        """``security audit`` runs a security audit and outputs results."""
        from aitbc_cli.commands.security import security

        result = runner.invoke(security, ["audit"])

        assert result.exit_code == 0, result.output
        assert "security_score" in result.output or "Security Audit" in result.output

    def test_security_scan_command(self, runner):
        """``security scan`` runs a security scan and outputs results."""
        from aitbc_cli.commands.security import security

        result = runner.invoke(security, ["scan"])

        assert result.exit_code == 0, result.output
        assert "security_scan" in result.output or "Security Scan" in result.output

    def test_security_patch_command(self, runner):
        """``security patch`` applies security patches and outputs results."""
        from aitbc_cli.commands.security import security

        result = runner.invoke(security, ["patch"])

        assert result.exit_code == 0, result.output
        assert "security_patch" in result.output or "Security Patch" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
