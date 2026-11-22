"""AUDIT-WORKFLOW-EXEC-ID-1 (#2561): ``workflow status``/``stop`` sent the
``--workflow-name`` value as the execution id. The executions status route
is keyed by execution id, and the cancel route needs the workflow id in the
path *and* ``execution_id`` as a query param.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from aitbc_cli.commands.workflow import status as status_cmd
from aitbc_cli.commands.workflow import stop as stop_cmd


def _config():
    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203"
    config.coordinator_api_key = "k"
    return config


def _ok(payload=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload or {"status": "RUNNING", "workflow_id": "wf1"}
    return resp


def test_status_uses_execution_id_in_url(runner=None):
    runner = runner or CliRunner()
    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=_config()),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}),
        patch("httpx.get", return_value=_ok()) as get,
    ):
        result = runner.invoke(status_cmd, ["--execution-id", "exec-42"], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert get.call_args[0][0] == "http://coord.example:8203/v1/agents/executions/exec-42/status"


def test_status_requires_execution_id_not_name():
    result = CliRunner().invoke(status_cmd, ["--workflow-name", "wf1"], obj={"output_format": "table"})
    assert result.exit_code == 2


def test_stop_sends_workflow_path_and_execution_param(runner=None):
    runner = runner or CliRunner()
    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=_config()),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}),
        patch("httpx.post", return_value=_ok({"status": "CANCELLED"})) as post,
    ):
        result = runner.invoke(
            stop_cmd,
            ["--workflow-name", "gpu-market", "--execution-id", "exec-42"],
            obj={"output_format": "table"},
        )
    assert result.exit_code == 0, result.output
    args, kwargs = post.call_args
    assert args[0] == "http://coord.example:8203/v1/agents/workflows/gpu-market/cancel"
    assert kwargs["params"] == {"execution_id": "exec-42"}


def test_stop_requires_execution_id():
    result = CliRunner().invoke(stop_cmd, ["--workflow-name", "gpu-market"], obj={"output_format": "table"})
    assert result.exit_code == 2
