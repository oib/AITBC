"""
Security Commands Tests
Tests for security CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import json

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

    def test_security_patch_reports_simulated_not_completed(self, runner):
        """#2220: the patch stub must say simulated — 'completed' implied
        patches were really applied."""
        from aitbc_cli.commands.security import security

        result = runner.invoke(security, ["patch"], obj={"output_format": "json"})

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["status"] == "simulated"
        assert data["status"] != "completed"

    def test_security_scan_reports_simulated(self, runner):
        """#2220: scan is a static stub — label it simulated like compliance check."""
        from aitbc_cli.commands.security import security

        result = runner.invoke(security, ["scan"], obj={"output_format": "json"})

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["status"] == "simulated"

    def test_security_audit_reports_simulated(self, runner):
        """#2220: audit returns a hardcoded score — label it simulated."""
        from aitbc_cli.commands.security import security

        result = runner.invoke(security, ["audit"], obj={"output_format": "json"})

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["status"] == "simulated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
