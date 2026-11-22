"""#2603 AUDIT-WORKFLOW-DRYRUN-NOOP-1 pins.

``workflow run --dry-run`` used to return before reading the config or
checking the workflow name — reporting "Would execute workflow" for an
unknown workflow and a missing config the real run refuses. It now loads
the config, verifies the workflow via GET /workflows/{id}, and prints the
request it would send.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from aitbc_cli.commands.workflow import workflow


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, args, get_side_effect=None, get_return=None):
    config_obj = SimpleNamespace(coordinator_api_url="http://coord.test", coordinator_api_key=None)
    httpx_mock = MagicMock()
    if get_side_effect is not None:
        httpx_mock.get.side_effect = get_side_effect
    else:
        httpx_mock.get.return_value = get_return or _resp(200, {"id": "wf"})
    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config_obj),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}),
        patch("httpx.get", httpx_mock.get),
        patch("httpx.post", httpx_mock.post),
    ):
        result = runner.invoke(workflow, ["run", "--workflow-name", "wf1", "--dry-run", *args])
    return result, httpx_mock


def _resp(status, body):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    r.text = json.dumps(body)
    return r


def test_dry_run_missing_config_refuses(runner, tmp_path):
    result, _ = _invoke(runner, ["--config", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
    assert "Config file not found" in result.output
    assert "Would execute" not in result.output


def test_dry_run_unknown_workflow_refuses(runner):
    result, mock = _invoke(runner, [], get_return=_resp(404, {"detail": "not found"}))
    assert result.exit_code != 0
    assert "Unknown workflow" in result.output
    assert "Would execute" not in result.output
    mock.post.assert_not_called()


def test_dry_run_valid_prints_request(runner, tmp_path):
    cfg = tmp_path / "wf.yaml"
    cfg.write_text(yaml.safe_dump({"steps": 1}))
    result, mock = _invoke(runner, ["--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "Would execute workflow without making changes" in result.output
    assert "POST http://coord.test/v1/agents/workflows/wf1/execute" in result.output
    assert '"workflow_id": "wf1"' in result.output
    assert '"steps": 1' in result.output
    mock.post.assert_not_called()  # dry-run never executes
