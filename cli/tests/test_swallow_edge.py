"""edge island/database refusals: benign idempotent answers stay rc 0.

CLI-SWALLOW-SWEEP-2 (#570) follow-up: c38c664a5 routed every
``{"success": false}`` answer to ``abort()``, but the edge service also
uses ``success:false`` for by-design idempotent outcomes:

- ``island bridge``: the only failure path in
  ``IslandManager.request_bridge`` is "already a member of the target
  island" (island_manager.py) — connectivity already exists, so rc 0.
- ``database init-db``: the only refusal is "Database <id> already
  exists" (database_service.py) — an idempotent re-init, so rc 0.
- ``island join``: already-member is ``success:true`` upstream; a
  ``success:false`` ("not known on this hub") is a real failure.
- ``island leave``: the service answers the identical "(may not be a
  member)" message for both "not a member" and "cannot leave the default
  island"; indistinguishable CLI-side, so refusals stay aborts.

The service sends no machine-readable code, so benign detection matches
on the exact message substrings in ``_BENIGN_REFUSAL_MARKERS``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import edge as edge_mod


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
    """stdout must contain exactly one JSON document carrying an ``error`` key."""
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


def test_join_unknown_island_aborts_table(runner):
    """The only real success:false upstream: island not known on this hub."""
    result = _invoke_edge(runner, JOIN_ARGV, {"success": False, "message": "Island island-1 is not known on this hub"})
    assert result.exit_code != 0
    assert "Failed to join island" in result.output


def test_join_unknown_island_aborts_json(runner):
    result = _invoke_edge(
        runner, JOIN_ARGV, {"success": False, "message": "Island island-1 is not known on this hub"}, fmt="json"
    )
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


def test_join_success_rc0(runner):
    result = _invoke_edge(runner, JOIN_ARGV, {"success": True, "status": "joined"})
    assert result.exit_code == 0


def test_join_already_member_rc0(runner):
    """Upstream answers success:true/status=already_member for a repeat join."""
    result = _invoke_edge(runner, JOIN_ARGV, {"success": True, "status": "already_member"})
    assert result.exit_code == 0


# --- edge island leave -------------------------------------------------------


def test_leave_not_member_aborts_table(runner):
    """Service conflates not-a-member with cannot-leave-default under one
    message, so the refusal stays an abort rather than risking a false rc 0."""
    argv = ["island", "leave", "--island-id", "island-1"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "Failed to leave island island-1 (may not be a member)"})
    assert result.exit_code != 0
    assert "Failed to leave island" in result.output


def test_leave_not_member_aborts_json(runner):
    argv = ["island", "leave", "--island-id", "island-1"]
    result = _invoke_edge(
        runner,
        argv,
        {"success": False, "message": "Failed to leave island island-1 (may not be a member)"},
        fmt="json",
    )
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


def test_leave_success_rc0(runner):
    argv = ["island", "leave", "--island-id", "island-1"]
    result = _invoke_edge(runner, argv, {"success": True, "status": "left"})
    assert result.exit_code == 0


# --- edge island bridge ------------------------------------------------------


def test_bridge_already_member_rc0_table(runner):
    """The service's only bridge failure is already-a-member: benign."""
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(
        runner,
        argv,
        {"success": False, "message": "Failed to request bridge to island-2 (may already be a member)"},
    )
    assert result.exit_code == 0
    assert "may already be a member" in result.output


def test_bridge_already_member_rc0_json(runner):
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(
        runner,
        argv,
        {"success": False, "message": "Failed to request bridge to island-2 (may already be a member)"},
        fmt="json",
    )
    assert result.exit_code == 0


def test_bridge_other_refusal_aborts_table(runner):
    """A refusal that is not the already-member marker still aborts."""
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "bridge quorum unavailable"})
    assert result.exit_code != 0
    assert "Failed to request bridge" in result.output


def test_bridge_other_refusal_aborts_json(runner):
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(runner, argv, {"success": False, "message": "bridge quorum unavailable"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


def test_bridge_success_rc0(runner):
    argv = ["island", "bridge", "--target-island-id", "island-2"]
    result = _invoke_edge(runner, argv, {"success": True, "request_id": "req-1", "status": "pending"})
    assert result.exit_code == 0


# --- edge database init-db ----------------------------------------------------

INIT_DB_ARGV = ["database", "init-db", "--database-id", "db-1", "--island-id", "i1", "--capacity-gb", "10"]


def test_init_db_already_exists_rc0_table(runner):
    """'already exists' is the service's only init-db refusal: benign."""
    result = _invoke_edge(runner, INIT_DB_ARGV, {"success": False, "message": "Database db-1 already exists"})
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_init_db_already_exists_rc0_json(runner):
    result = _invoke_edge(runner, INIT_DB_ARGV, {"success": False, "message": "Database db-1 already exists"}, fmt="json")
    assert result.exit_code == 0


def test_init_db_other_refusal_aborts_table(runner):
    result = _invoke_edge(runner, INIT_DB_ARGV, {"success": False, "message": "capacity exceeded"})
    assert result.exit_code != 0
    assert "Failed to initialize database" in result.output


def test_init_db_other_refusal_aborts_json(runner):
    result = _invoke_edge(runner, INIT_DB_ARGV, {"success": False, "message": "capacity exceeded"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


# --- serve submit-request / metrics record (no benign success:false exists) ---


def test_submit_request_refusal_aborts(runner):
    argv = [
        "serve",
        "submit-request",
        "--gpu-id",
        "gpu-1",
        "--model-name",
        "m1",
        "--input-data",
        '{"x": 1}',
    ]
    result = _invoke_edge(runner, argv, {"success": False, "message": "gpu busy"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)


def test_metrics_record_refusal_aborts(runner):
    argv = ["metrics", "record", "--gpu-id", "gpu-1", "--metrics", '{"temp": 60}']
    result = _invoke_edge(runner, argv, {"success": False, "message": "bad metrics"}, fmt="json")
    assert result.exit_code != 0
    _assert_single_error_doc(result.output)
