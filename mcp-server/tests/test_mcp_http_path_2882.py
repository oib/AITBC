"""AUDIT-EDGE-MCP-HTTP-PATH (#2882) + AUDIT-EDGE-MCP-READ-OPTS (#2883).

``call_aitbc_http`` passed ``path`` straight through to ``aitbc http call``:
a leading ``/`` escapes the service mount to the origin root (#2217), and
``..``/``?``/``#`` enabled endpoint confusion — GET needs no confirm. Every
typed read tool interpolating a free-form id shared the hole. Paths are now
validated in ``_run_http`` and ``call_aitbc_http``.

``read_aitbc_cli`` and ``_aitbc_cli_read_tool`` are ``read_only_hint=True``
with no confirm gate, so mutation-looking option names are now refused
outright — the same heuristic ``run_aitbc_cli`` uses to force confirmation.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server


# ---------------------------------------------------------------------------
# #2882 — http path validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "info",
        "account/0x" + "ab" * 20,
        "v1/jobs",
        "blocks-range",
        "bridge/block-headers/mainnet/123",
    ],
)
def test_validate_http_path_accepts_normal_paths(path):
    assert mcp_server._validate_http_path(path) is None


@pytest.mark.parametrize(
    "path",
    [
        "/health",  # leading '/' escapes the service mount to origin root
        "x/../../admin",
        "a/./b",
        "foo?bar=baz",  # query injection
        "a#fragment",
        "a//b",
        "a/",
        "%2e%2e/x",
        "a%2fb",
        "a b",
        "",
        "   ",
    ],
)
def test_validate_http_path_rejects_unsafe(path):
    assert mcp_server._validate_http_path(path) is not None


def test_run_http_refuses_bad_path_before_remote_call():
    spy = mock.Mock(return_value={"returncode": 0, "stdout": "{}"})
    with mock.patch.object(mcp_server, "_run_aitbc_cli", spy):
        out = mcp_server._run_http("node2", "blockchain-rpc", "/health")
    assert "error" in out
    spy.assert_not_called()


def test_run_http_allows_normal_path():
    spy = mock.Mock(return_value={"returncode": 0, "stdout": "{}"})
    with mock.patch.object(mcp_server, "_run_aitbc_cli", spy):
        mcp_server._run_http("node2", "blockchain-rpc", "info")
    spy.assert_called_once()
    assert spy.call_args[0][3] == ["blockchain-rpc", "info"]


def test_call_aitbc_http_dry_run_refuses_bad_path():
    out = json.loads(mcp_server.call_aitbc_http(service="blockchain-rpc", path="x/../admin", dry_run=True, host="node2"))
    assert "error" in out
    assert "invalid http path" in out["error"]


def test_call_aitbc_http_confirm_gate_still_works_for_mutating():
    out = json.loads(
        mcp_server.call_aitbc_http(service="coordinator-api", path="v1/jobs", method="POST", body={"a": 1}, host="node2")
    )
    assert "Confirmation required" in out.get("error", "")


# ---------------------------------------------------------------------------
# #2883 — read-only tools refuse mutation-looking options
# ---------------------------------------------------------------------------


def test_read_aitbc_cli_refuses_mutation_looking_option():
    out = json.loads(
        mcp_server.read_aitbc_cli(
            group="wallet",
            subcommand=["list"],
            options={"send": "0xabc 1.0"},
            host="node2",
        )
    )
    assert "mutating" in out.get("error", "")


def test_read_aitbc_cli_refuses_mutation_group_option():
    out = json.loads(
        mcp_server.read_aitbc_cli(
            group="wallet",
            subcommand=["list"],
            group_options={"delete": None},
            host="node2",
        )
    )
    assert "mutating" in out.get("error", "")


def test_aitbc_cli_read_tool_refuses_mutation_looking_option():
    """Typed read tools with user-controlled ``options`` get the same refusal."""
    out = json.loads(mcp_server._aitbc_cli_read_tool(None, "node2", "market", "list", options={"delete": "everything"}))
    assert "mutating" in out.get("error", "")


def test_aitbc_cli_read_tool_allows_normal_options():
    spy = mock.Mock(return_value={"returncode": 0, "stdout": "{}"})
    with mock.patch.object(mcp_server, "_run_remote", spy):
        out = json.loads(mcp_server._aitbc_cli_read_tool(None, "node2", "market", "list", options={"limit": "5"}))
    assert "error" not in out or "mutating" not in out.get("error", "")
    spy.assert_called_once()
