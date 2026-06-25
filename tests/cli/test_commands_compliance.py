"""
Compliance Commands Tests
Tests for compliance CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest


class TestComplianceCommands:
    """Test compliance command group"""

    def test_compliance_group_exists(self):
        """Test that compliance command group exists"""
        from aitbc_cli.commands.compliance import compliance

        assert compliance is not None
        assert hasattr(compliance, "name")

    def test_compliance_group_name(self):
        """Test compliance group name"""
        from aitbc_cli.commands.compliance import compliance

        assert compliance.name == "compliance"

    def test_compliance_group_has_check_subcommand(self):
        """The ``check`` subcommand is registered on the compliance group."""
        from aitbc_cli.commands.compliance import compliance

        assert "check" in compliance.commands

    def test_compliance_group_has_report_subcommand(self):
        """The ``report`` subcommand is registered on the compliance group."""
        from aitbc_cli.commands.compliance import compliance

        assert "report" in compliance.commands

    def test_compliance_check_command(self, runner):
        """``compliance check`` runs a compliance check and reports results."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check"])

        assert result.exit_code == 0, result.output
        assert "compliant" in result.output

    def test_compliance_check_with_standard(self, runner):
        """``compliance check --standard GDPR`` checks against the GDPR standard."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check", "--standard", "GDPR"])

        assert result.exit_code == 0, result.output
        assert "GDPR" in result.output

    def test_compliance_report_command(self, runner):
        """``compliance report`` generates a compliance report."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["report"])

        assert result.exit_code == 0, result.output
        assert "generated" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
