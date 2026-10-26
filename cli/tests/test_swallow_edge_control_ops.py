"""edge/control/operations commands must abort non-zero on refusals.

CLI-SWALLOW-SWEEP-2 (#570): these commands printed an error and then
returned normally, so scripted callers saw exit 0 on failure. The refusal
paths now route through ``abort()`` like mining.py / coin_requests.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import edge as edge_mod
from aitbc_cli.commands import control as control_mod
from aitbc_cli.commands import operations as ops_mod


@pytest.fixture
def runner():
    return CliRunner()


class _Resp:
    """httpx-style response stub returning a fixed JSON body."""

    def __init__(self, body):
        self._body = body
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _edge_client(body):
    client = MagicMock()
    client.post.return_value = _Resp(body)
    client.get.return_value = _Resp(body)
    return client


def _invoke_edge(runner, argv, body, fmt="table"):
    with patch.object(edge_mod, "get_edge_client", return_value=_edge_client(body)):
        return runner.invoke(edge_mod.edge, argv, obj={"output_format": fmt})


def _assert_single_error_doc(output: str):
    """stdout must contain exactly one JSON document carrying an ``error`` key.

    CliRunner merges stderr into stdout, so a click ``deprecated=True`` banner
    may precede the document; parse from the first ``{`` — any second JSON doc
    or trailing text still fails the decode.
    """
    start = output.find("{")
    assert start != -1, output
    doc = json.loads(output[start:])
    assert "error" in doc, output


# --- edge island join --------------------------------------------------------


JOIN_ARGV = [
    "island",
    "join",
    "--island-id",
    "island-1",
    "--island-name",
    "hub",
    "--chain-id",
    "ait-mainnet",
    "--confirm",
]


def test_edge_join_refusal_aborts_table(runner):
    result = _invoke_edge(runner, JOIN_ARGV, {"success": False, "message": "duplicate island"})
    assert result.exit_code != 0
    assert "Failed to join island" in result.output


def test_edge_join_refusal_aborts_json(runner):
    result = _invoke_edge(runner, JOIN_ARGV, {"success": False, "message": "duplicate island"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


def test_edge_join_success_rc0(runner):
    result = _invoke_edge(runner, JOIN_ARGV, {"success": True})
    assert result.exit_code == 0


# --- edge island leave -------------------------------------------------------


def test_edge_leave_refusal_aborts_table(runner):
    argv = ["island", "leave", "--island-id", "island-1"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "not a member"})
    assert result.exit_code != 0
    assert "Failed to leave island" in result.output


def test_edge_leave_refusal_aborts_json(runner):
    argv = ["island", "leave", "--island-id", "island-1"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "not a member"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- edge island bridge ------------------------------------------------------


def test_edge_bridge_refusal_aborts_table(runner):
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "no route"})
    assert result.exit_code != 0
    assert "Failed to request bridge" in result.output


def test_edge_bridge_refusal_aborts_json(runner):
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "no route"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- edge database init-db ---------------------------------------------------


def test_edge_init_db_refusal_aborts_table(runner):
    argv = ["database", "init-db", "--database-id", "db-1", "--island-id", "i1", "--capacity-gb", "10"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "capacity exceeded"})
    assert result.exit_code != 0
    assert "Failed to initialize database" in result.output


def test_edge_init_db_refusal_aborts_json(runner):
    argv = ["database", "init-db", "--database-id", "db-1", "--island-id", "i1", "--capacity-gb", "10"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "capacity exceeded"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- edge serve submit-request -----------------------------------------------


SUBMIT_ARGV = [
    "serve",
    "submit-request",
    "--gpu-id",
    "gpu-1",
    "--model-name",
    "m1",
    "--input-data",
    '{"x": 1}',
]


def test_edge_submit_request_refusal_aborts_table(runner):
    result = _invoke_edge(runner, SUBMIT_ARGV, {"success": False, "message": "gpu busy"})
    assert result.exit_code != 0
    assert "Failed to submit request" in result.output


def test_edge_submit_request_refusal_aborts_json(runner):
    result = _invoke_edge(runner, SUBMIT_ARGV, {"success": False, "message": "gpu busy"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- edge metrics record -----------------------------------------------------


def test_edge_metrics_record_refusal_aborts_table(runner):
    argv = ["metrics", "record", "--gpu-id", "gpu-1", "--metrics", '{"temp": 60}']
    result = _invoke_edge(runner, argv, {"success": False, "message": "bad metrics"})
    assert result.exit_code != 0
    assert "Failed to record metrics" in result.output


def test_edge_metrics_record_refusal_aborts_json(runner):
    argv = ["metrics", "record", "--gpu-id", "gpu-1", "--metrics", '{"temp": 60}']
    result = _invoke_edge(runner, argv, {"success": False, "message": "bad metrics"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- control start/stop/restart ----------------------------------------------


def _invoke_control(runner, command, fmt="table", rc=1):
    def _run(cmd, **kw):
        res = MagicMock()
        res.returncode = rc
        res.stderr = "unit failed" if rc else ""
        res.stdout = "" if rc else "ok"
        return res

    with (
        patch.object(control_mod, "_role_services", return_value=["aitbc-a.service", "aitbc-b.service"]),
        patch.object(control_mod, "_systemctl_prefix", return_value=[]),
        patch.object(control_mod.subprocess, "run", side_effect=_run),
    ):
        return runner.invoke(command, [], obj={"output_format": fmt})


def test_control_start_failed_unit_aborts_table(runner):
    result = _invoke_control(runner, control_mod.start)
    assert result.exit_code != 0


def test_control_start_failed_unit_aborts_json(runner):
    result = _invoke_control(runner, control_mod.start, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


def test_control_stop_failed_unit_aborts(runner):
    result = _invoke_control(runner, control_mod.stop)
    assert result.exit_code != 0


def test_control_restart_failed_unit_aborts(runner):
    result = _invoke_control(runner, control_mod.restart)
    assert result.exit_code != 0


def test_control_start_success_rc0(runner):
    result = _invoke_control(runner, control_mod.start, rc=0)
    assert result.exit_code == 0


# --- operations agent list ---------------------------------------------------


def test_ops_agent_list_non200_aborts_table(runner, monkeypatch):
    resp = MagicMock()
    resp.status_code = 500
    monkeypatch.setattr("requests.post", lambda *a, **kw: resp)
    result = runner.invoke(ops_mod.operations, ["agent", "list"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "Error listing agents" in result.output


def test_ops_agent_list_non200_aborts_json(runner, monkeypatch):
    resp = MagicMock()
    resp.status_code = 500
    monkeypatch.setattr("requests.post", lambda *a, **kw: resp)
    result = runner.invoke(ops_mod.operations, ["agent", "list"], obj={"output_format": "json"})
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- operations ai submit-job ------------------------------------------------


SUBMIT_JOB_ARGV = [
    "ai",
    "submit-job",
    "--wallet-name",
    "no-such-wallet",
    "--job-type",
    "infer",
    "--prompt",
    "hello",
    "--payment",
    "10",
]


def test_ops_submit_job_wallet_missing_aborts_table(runner, monkeypatch):
    monkeypatch.setattr(ops_mod, "find_wallet_file", lambda name: None)
    result = runner.invoke(ops_mod.operations, SUBMIT_JOB_ARGV, obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "not found" in result.output


def test_ops_submit_job_wallet_missing_aborts_json(runner, monkeypatch):
    monkeypatch.setattr(ops_mod, "find_wallet_file", lambda name: None)
    result = runner.invoke(ops_mod.operations, SUBMIT_JOB_ARGV, obj={"output_format": "json"})
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)
