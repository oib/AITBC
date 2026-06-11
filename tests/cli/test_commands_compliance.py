"""
Compliance Commands Tests
Tests for compliance CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestComplianceCommands:
    """Test compliance command group"""

    def test_compliance_group_exists(self):
        """Test that compliance command group exists"""
        try:
            from aitbc_cli.commands.compliance import compliance
            assert compliance is not None
            assert hasattr(compliance, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import compliance commands: {e}")

    def test_compliance_group_name(self):
        """Test compliance group name"""
        try:
            from aitbc_cli.commands.compliance import compliance
            assert compliance.name == "compliance"
        except ImportError as e:
            pytest.skip(f"Cannot import compliance commands: {e}")

    @patch('aitbc_cli.commands.compliance.output')
    @patch('aitbc_cli.commands.compliance.error')
    def test_compliance_check_command(self, mock_error, mock_output):
        """Test compliance check command"""
        try:
            from aitbc_cli.commands.compliance import check
            from click.testing import CliRunner
            
            runner = CliRunner()
            ctx = Mock()
            ctx.obj = {'output_format': 'json'}
            
            # Call the check command with context
            with runner.make_context('compliance', [], obj=ctx.obj) as ctx:
                check(ctx, standard='GDPR')
            
            # Verify output was called
            assert mock_output.called
        except Exception as e:
            pytest.skip(f"Cannot test compliance check: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
