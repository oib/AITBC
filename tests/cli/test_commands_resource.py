"""Tests for the current agent resource CLI commands."""

from unittest.mock import MagicMock, patch


def test_resource_group_has_current_subcommands():
    """The resource group exposes the coordinator-backed commands."""
    from aitbc_cli.commands.resource import resource

    assert set(resource.commands) == {"allocate", "optimize"}


def test_resource_allocate_command(runner):
    """Resource allocation posts the requested requirements."""
    from aitbc_cli.commands import resource as resource_module

    client = MagicMock()
    client.post.return_value = {"allocation_id": "alloc-1"}
    with patch.object(resource_module, "_client", return_value=client):
        result = runner.invoke(resource_module.resource, ["allocate", "--agent-id", "agent-1", "--cpu-cores", "2"])

    assert result.exit_code == 0, result.output
    client.post.assert_called_once_with(
        "/v1/agent-performance/resources/allocate",
        json={
            "agent_id": "agent-1",
            "task_requirements": {"cpu_cores": 2.0},
            "optimization_target": "efficiency",
            "priority_level": "normal",
        },
    )


def test_resource_optimize_command(runner):
    """Resource optimization posts the selected performance metric."""
    from aitbc_cli.commands import resource as resource_module

    client = MagicMock()
    client.post.return_value = {"optimization_id": "opt-1"}
    with patch.object(resource_module, "_client", return_value=client):
        result = runner.invoke(
            resource_module.resource,
            ["optimize", "--agent-id", "agent-1", "--target-metric", "accuracy", "--current-accuracy", "0.9"],
        )

    assert result.exit_code == 0, result.output
    client.post.assert_called_once_with(
        "/v1/agent-performance/optimize",
        json={
            "agent_id": "agent-1",
            "target_metric": "accuracy",
            "current_performance": {"accuracy": 0.9},
            "optimization_type": "comprehensive",
        },
    )
