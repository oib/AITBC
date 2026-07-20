"""Compatibility coverage for the current resource command group."""

from unittest.mock import MagicMock, patch


def test_resource_commands_are_current():
    """The resource command surface matches the agent-performance API."""
    from aitbc_cli.commands.resource import resource

    assert set(resource.commands) == {"allocate", "optimize"}


def test_resource_commands_reject_missing_requirements(runner):
    """Allocation and optimization require their request data."""
    from aitbc_cli.commands.resource import resource

    allocate_result = runner.invoke(resource, ["allocate", "--agent-id", "agent-1"])
    optimize_result = runner.invoke(resource, ["optimize", "--agent-id", "agent-1", "--target-metric", "accuracy"])

    assert allocate_result.exit_code != 0
    assert optimize_result.exit_code != 0


def test_resource_commands_use_http_client(runner):
    """Current commands delegate requests to the coordinator API client."""
    from aitbc_cli.commands import resource as resource_module

    client = MagicMock()
    client.post.return_value = {}
    with patch.object(resource_module, "_client", return_value=client):
        result = runner.invoke(
            resource_module.resource,
            ["allocate", "--agent-id", "agent-1", "--gpu-count", "1"],
        )

    assert result.exit_code == 0, result.output
    assert client.post.call_args.args[0] == "/v1/agent-performance/resources/allocate"
