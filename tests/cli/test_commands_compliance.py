"""
Compliance Commands Tests
Tests for compliance CLI commands

These previously targeted the pre-v0.15.2 command surface: a ``check --standard GDPR``
that returned a hardcoded ``{"compliance_level": "compliant"}`` and a ``report`` subcommand
that returned ``{"status": "generated"}`` without generating anything. Commit 64e1bf1ed
("feat(v0.15.2): B1/B3 compliance containers, middleware, CLI and tests") replaced both
stubs with real policy evaluation, but these tests were never updated -- so they failed
against every build since.

They now exercise the actual surface: ``check``, ``classify`` and ``export-audit``,
asserting real policy outcomes (hipaa permits phi but not pci) rather than fixed strings.
"""

import json

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

    def test_compliance_group_subcommands(self):
        """The compliance group exposes exactly the v0.15.2 B3 command surface."""
        from aitbc_cli.commands.compliance import compliance

        assert set(compliance.commands) == {"check", "classify", "export-audit"}


class TestComplianceCheck:
    """``compliance check`` evaluates a classification against a framework policy."""

    def test_check_defaults_to_hipaa_phi(self, runner):
        """With no options it checks phi against hipaa, which permits it."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check"])

        assert result.exit_code == 0, result.output
        assert '"framework": "hipaa"' in result.output
        assert '"classification": "phi"' in result.output
        assert '"allowed": true' in result.output

    def test_check_reports_policy_id(self, runner):
        """The resolved policy is identified in the output, not just the verdict."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check"])

        assert result.exit_code == 0, result.output
        assert '"policy_id": "hipaa-v1"' in result.output

    def test_check_disallowed_classification_reports_false(self, runner):
        """hipaa does not permit pci -- the command must say so rather than pass everything."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check", "--framework", "hipaa", "--classification", "pci"])

        assert result.exit_code == 0, result.output
        assert '"allowed": false' in result.output

    @pytest.mark.parametrize("framework", ["hipaa", "soc2", "pci_dss", "generic"])
    def test_check_accepts_each_supported_framework(self, runner, framework):
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check", "--framework", framework, "--classification", "internal"])

        assert result.exit_code == 0, result.output
        assert f'"framework": "{framework}"' in result.output

    def test_check_rejects_unknown_framework(self, runner):
        """An unrecognised framework must fail, not fall back to a permissive default."""
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["check", "--framework", "not-a-framework"])

        assert result.exit_code != 0


class TestComplianceClassify:
    """``compliance classify`` normalizes a data classification label."""

    def test_classify_normalizes_case(self, runner):
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["classify", "PHI"])

        assert result.exit_code == 0, result.output
        assert '"normalized": "phi"' in result.output

    def test_classify_flags_sensitive_label(self, runner):
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["classify", "pii"])

        assert result.exit_code == 0, result.output
        assert '"sensitive": true' in result.output

    def test_classify_flags_non_sensitive_label(self, runner):
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["classify", "public"])

        assert result.exit_code == 0, result.output
        assert '"sensitive": false' in result.output

    def test_classify_requires_a_label(self, runner):
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["classify"])

        assert result.exit_code != 0

    def test_classify_rejects_unknown_label(self, runner):
        from aitbc_cli.commands.compliance import compliance

        result = runner.invoke(compliance, ["classify", "not-a-classification"])

        assert result.exit_code != 0


class TestComplianceExportAudit:
    """``compliance export-audit`` writes an audit trail to disk."""

    def test_export_audit_writes_json_file(self, runner, tmp_path):
        from aitbc_cli.commands.compliance import compliance

        target = tmp_path / "audit.json"
        result = runner.invoke(compliance, ["export-audit", "--output-file", str(target)])

        assert result.exit_code == 0, result.output
        assert target.exists()

        payload = json.loads(target.read_text())
        assert "exported_at" in payload
        assert isinstance(payload["records"], list)

    def test_export_audit_records_carry_expected_fields(self, runner, tmp_path):
        from aitbc_cli.commands.compliance import compliance

        target = tmp_path / "audit.json"
        result = runner.invoke(compliance, ["export-audit", "--output-file", str(target)])

        assert result.exit_code == 0, result.output
        records = json.loads(target.read_text())["records"]

        assert records, "export produced no audit records"
        for record in records:
            assert {"timestamp", "actor_id", "action", "resource_id", "outcome"} <= set(record)

    def test_export_audit_reports_record_count(self, runner, tmp_path):
        """The reported count must match what actually landed in the file."""
        from aitbc_cli.commands.compliance import compliance

        target = tmp_path / "audit.json"
        result = runner.invoke(compliance, ["export-audit", "--output-file", str(target)])

        assert result.exit_code == 0, result.output
        written = len(json.loads(target.read_text())["records"])
        assert f'"record_count": {written}' in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
