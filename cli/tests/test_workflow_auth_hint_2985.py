"""#2985 COORD-WORKFLOW-API-KEY-401-1 pins.

The coordinator's workflow/execution routes are AdminDep-gated, so an
unauthenticated caller draws the middleware's bare ``401 Authentication
required`` — the S66 play saw exactly that with no hint of which credential
to provision. Every workflow command now maps 401 (anonymous / bad
credential) and 403 (non-admin role) to the same admin-login guidance.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.workflow import workflow


@pytest.fixture
def runner():
    return CliRunner()


def _resp(status, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body if body is not None else {"detail": "Authentication required"}
    r.text = json.dumps(r.json.return_value)
    return r


def _invoke(runner, args, get_return=None, post_return=None):
    config_obj = SimpleNamespace(coordinator_api_url="http://coord.test", coordinator_api_key=None)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value = get_return or _resp(200, {})
    httpx_mock.post.return_value = post_return or _resp(200, {})
    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config_obj),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={"Authorization": "Bearer tok"}),
        patch("httpx.get", httpx_mock.get),
        patch("httpx.post", httpx_mock.post),
    ):
        result = runner.invoke(workflow, args)
    return result, httpx_mock


@pytest.mark.parametrize("status", [401, 403])
def test_list_maps_auth_failures_to_admin_hint(runner, status):
    result, _ = _invoke(runner, ["list"], get_return=_resp(status))
    assert result.exit_code != 0
    assert "admin-role credential" in result.output
    assert "auth login --credential-name admin" in result.output


@pytest.mark.parametrize("status", [401, 403])
def test_run_maps_auth_failures_to_admin_hint(runner, status):
    result, mock = _invoke(
        runner,
        ["run", "--workflow-name", "wf1"],
        post_return=_resp(status),
    )
    assert result.exit_code != 0
    assert "admin-role credential" in result.output
    mock.post.assert_called_once()


@pytest.mark.parametrize("status", [401, 403])
def test_status_maps_auth_failures_to_admin_hint(runner, status):
    result, _ = _invoke(runner, ["status", "--execution-id", "ex-1"], get_return=_resp(status))
    assert result.exit_code != 0
    assert "admin-role credential" in result.output


@pytest.mark.parametrize("status", [401, 403])
def test_stop_maps_auth_failures_to_admin_hint(runner, status):
    result, _ = _invoke(
        runner,
        ["stop", "--workflow-name", "wf1", "--execution-id", "ex-1"],
        post_return=_resp(status),
    )
    assert result.exit_code != 0
    assert "admin-role credential" in result.output


def test_dry_run_lookup_401_maps_to_admin_hint(runner):
    """The dry-run's workflow-existence GET hits the same gate."""
    result, _ = _invoke(
        runner,
        ["run", "--workflow-name", "wf1", "--dry-run"],
        get_return=_resp(401),
    )
    assert result.exit_code != 0
    assert "admin-role credential" in result.output
    assert "Would execute" not in result.output
