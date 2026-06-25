"""
Resource Commands Tests
Tests for resource CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestResourceCommands:
    """Test resource command group"""

    def test_resource_group_exists(self):
        """Test that resource command group exists"""
        from aitbc_cli.commands.resource import resource

        assert resource is not None
        assert hasattr(resource, "name")

    def test_resource_group_name(self):
        """Test resource group name"""
        from aitbc_cli.commands.resource import resource

        assert resource.name == "resource"

    def test_resource_group_has_allocate_subcommand(self):
        """The ``allocate`` subcommand is registered on the resource group."""
        from aitbc_cli.commands.resource import resource

        assert "allocate" in resource.commands

    def test_resource_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the resource group."""
        from aitbc_cli.commands.resource import resource

        assert "list" in resource.commands

    def test_resource_group_has_release_subcommand(self):
        """The ``release`` subcommand is registered on the resource group."""
        from aitbc_cli.commands.resource import resource

        assert "release" in resource.commands

    def test_resource_group_has_utilization_subcommand(self):
        """The ``utilization`` subcommand is registered on the resource group."""
        from aitbc_cli.commands.resource import resource

        assert "utilization" in resource.commands

    def test_resource_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the resource group."""
        from aitbc_cli.commands.resource import resource

        assert "status" in resource.commands

    def test_resource_allocate_command_mock(self, runner):
        """``resource allocate --mock`` allocates resources with mock data."""
        from aitbc_cli.commands.resource import resource

        result = runner.invoke(
            resource,
            ["allocate", "--resource-type", "gpu", "--quantity", "4", "--mock"],
        )

        assert result.exit_code == 0, result.output
        assert "alloc_" in result.output

    def test_resource_allocate_command_without_mock_aborts(self, runner):
        """``resource allocate`` without --mock aborts."""
        from aitbc_cli.commands.resource import resource

        result = runner.invoke(
            resource,
            ["allocate", "--resource-type", "gpu", "--quantity", "4"],
        )

        assert result.exit_code != 0

    def test_resource_list_command_mock(self, runner):
        """``resource list --mock`` lists allocated resources."""
        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["list", "--mock"])

        assert result.exit_code == 0, result.output
        assert "gpu" in result.output.lower()

    def test_resource_release_command_mock(self, runner):
        """``resource release --mock`` releases a resource."""
        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["release", "res-123", "--mock"])

        assert result.exit_code == 0, result.output
        assert "res-123" in result.output

    def test_resource_utilization_command_mock(self, runner):
        """``resource utilization --mock`` shows utilization metrics."""
        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["utilization", "--mock"])

        assert result.exit_code == 0, result.output
        assert "cpu_utilization" in result.output

    def test_resource_optimize_command_mock(self, runner):
        """``resource optimize --mock`` runs optimization with mock data."""
        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["optimize", "--mock"])

        assert result.exit_code == 0, result.output
        assert "mock" in result.output

    @patch("aitbc_cli.commands.resource.get_config")
    @patch("aitbc_cli.commands.resource.AITBCHTTPClient")
    def test_resource_status_command(self, mock_http_class, mock_get_config, runner, mock_blockchain_rpc):
        """``resource status`` fetches resource status from coordinator-api."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "healthy", "resources": 10}

        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()

    @patch("aitbc_cli.commands.resource.get_config")
    @patch("aitbc_cli.commands.resource.AITBCHTTPClient")
    def test_resource_status_with_resource_id(self, mock_http_class, mock_get_config, runner):
        """``resource status --resource-id`` fetches a specific resource."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"resource_id": "res-123", "status": "active"}

        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["status", "--resource-id", "res-123"])

        assert result.exit_code == 0, result.output
        requested_path = mock_client.get.call_args[0][0]
        assert "res-123" in requested_path

    @patch("aitbc_cli.commands.resource.get_config")
    @patch("aitbc_cli.commands.resource.AITBCHTTPClient")
    def test_resource_deallocate_command(self, mock_http_class, mock_get_config, runner):
        """``resource deallocate --force`` deallocates a resource."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "deallocated"}

        from aitbc_cli.commands.resource import resource

        result = runner.invoke(resource, ["deallocate", "res-123", "--force"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "res-123" in mock_client.post.call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
