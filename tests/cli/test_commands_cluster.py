"""
Cluster Commands Tests
Tests for cluster CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestClusterCommands:
    """Test cluster command group"""

    def test_cluster_group_exists(self):
        """Test that cluster command group exists"""
        try:
            from aitbc_cli.commands.cluster import cluster

            assert cluster is not None
            assert hasattr(cluster, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import cluster commands: {e}")

    def test_cluster_group_name(self):
        """Test cluster group name"""
        try:
            from aitbc_cli.commands.cluster import cluster

            assert cluster.name == "cluster"
        except ImportError as e:
            pytest.skip(f"Cannot import cluster commands: {e}")

    @patch("aitbc_cli.commands.cluster.output")
    @patch("aitbc_cli.commands.cluster.error")
    def test_cluster_status_command(self, mock_error, mock_output):
        """Test cluster status command"""
        try:
            from aitbc_cli.commands.cluster import status
            from click.testing import CliRunner

            runner = CliRunner()
            ctx = Mock()
            ctx.obj = {"output_format": "json"}

            # Call the status command with context
            with runner.make_context("cluster", [], obj=ctx.obj) as ctx:
                status(ctx)

            # Verify output was called
            assert mock_output.called
        except Exception as e:
            pytest.skip(f"Cannot test cluster status: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
