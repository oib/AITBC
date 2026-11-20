"""MCP mutating tools for DAO governance profile bootstrap (#2337).

``init_governance_profile`` / ``delegate_governance_votes`` /
``set_governance_voting_power`` wrap ``aitbc governance profile
init|delegate|power`` and are destructive-gated like the other mutating
wrappers: dry-run envelope by default, refusal without ``confirm``,
execution only with both.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server

mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}

import aitbc_mcp_mutating_tools  # noqa: E402


def _recorder(captured: list[dict[str, object]]):
    def _fake(host: str, command: str, timeout: int = 60) -> dict[str, object]:
        captured.append({"host": host, "command": command, "timeout": timeout})
        return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

    return _fake


def test_init_governance_profile_dry_run_default():
    result = json.loads(aitbc_mcp_mutating_tools.init_governance_profile(user_id="0xAlice", voting_power=10.0))
    assert result.get("dry_run") is True
    assert "command" in result


def test_init_governance_profile_requires_confirm():
    captured: list[dict[str, object]] = []
    with mock.patch.object(mcp_server, "_run_remote", _recorder(captured)):
        result = json.loads(
            aitbc_mcp_mutating_tools.init_governance_profile(
                user_id="0xAlice", voting_power=10.0, dry_run=False, confirm=False
            )
        )
    assert "error" in result
    assert captured == []


def test_init_governance_profile_executes_with_confirm():
    captured: list[dict[str, object]] = []
    with mock.patch.object(mcp_server, "_run_remote", _recorder(captured)):
        result = json.loads(
            aitbc_mcp_mutating_tools.init_governance_profile(user_id="0xAlice", voting_power=10.0, dry_run=False, confirm=True)
        )
    assert result.get("returncode") == 0
    assert len(captured) == 1
    assert "governance" in captured[0]["command"]
    assert "profile" in captured[0]["command"]
    assert "init" in captured[0]["command"]
    assert "--user-id" in captured[0]["command"]


def test_delegate_and_power_wrap_expected_subcommands():
    captured: list[dict[str, object]] = []
    with mock.patch.object(mcp_server, "_run_remote", _recorder(captured)):
        aitbc_mcp_mutating_tools.delegate_governance_votes(
            profile_id="prof-1", delegatee_id="prof-2", dry_run=False, confirm=True
        )
        aitbc_mcp_mutating_tools.set_governance_voting_power(
            profile_id="prof-1", voting_power=5.0, dry_run=False, confirm=True
        )
    assert len(captured) == 2
    assert "delegate" in captured[0]["command"]
    assert "power" in captured[1]["command"]
