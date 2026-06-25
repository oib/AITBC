"""
Cluster Commands Tests
Tests for cluster CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest


class TestClusterCommands:
    """Test cluster command group"""

    def test_cluster_group_exists(self):
        """Test that cluster command group exists"""
        from aitbc_cli.commands.cluster import cluster

        assert cluster is not None
        assert hasattr(cluster, "name")

    def test_cluster_group_name(self):
        """Test cluster group name"""
        from aitbc_cli.commands.cluster import cluster

        assert cluster.name == "cluster"

    def test_cluster_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the cluster group."""
        from aitbc_cli.commands.cluster import cluster

        assert "status" in cluster.commands

    def test_cluster_group_has_sync_subcommand(self):
        """The ``sync`` subcommand is registered on the cluster group."""
        from aitbc_cli.commands.cluster import cluster

        assert "sync" in cluster.commands

    def test_cluster_group_has_balance_subcommand(self):
        """The ``balance`` subcommand is registered on the cluster group."""
        from aitbc_cli.commands.cluster import cluster

        assert "balance" in cluster.commands

    def test_cluster_status_command(self, runner):
        """``cluster status`` returns cluster health status."""
        from aitbc_cli.commands.cluster import cluster

        result = runner.invoke(cluster, ["status"])

        assert result.exit_code == 0, result.output
        assert "healthy" in result.output

    def test_cluster_sync_command(self, runner):
        """``cluster sync`` reports sync completion."""
        from aitbc_cli.commands.cluster import cluster

        result = runner.invoke(cluster, ["sync"])

        assert result.exit_code == 0, result.output
        assert "completed" in result.output

    def test_cluster_balance_command(self, runner):
        """``cluster balance`` reports balance completion."""
        from aitbc_cli.commands.cluster import cluster

        result = runner.invoke(cluster, ["balance"])

        assert result.exit_code == 0, result.output
        assert "completed" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
