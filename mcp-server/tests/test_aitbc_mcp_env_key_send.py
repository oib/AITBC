"""MCP tool ``send_aitbc_from_env_key`` wraps ``transactions send --key-env`` (#2328).

The tool is destructive-gated like its wallet sibling: a dry-run envelope by
default, a refusal without ``confirm``, and execution only with both. On
execution it forwards ``--key-env <NAME> --yes`` — the env var NAME only,
never key material — plus ``--yes`` because the MCP confirm gate replaces the
CLI's interactive prompt.

``_run_remote`` is patched per-test (``mock.patch.object``) rather than
replaced at import time: test_aitbc_mcp_cli_tools.py owns the session-wide
recorder, and a second import-time patch would silently steal its calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server

# Deterministic role map — same convention as test_aitbc_mcp_cli_tools.py.
mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}

import aitbc_mcp_mutating_tools  # noqa: E402

TO = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


def _recorder(captured: list[dict[str, object]]):
    def _fake(host: str, command: str, timeout: int = 60) -> dict[str, object]:
        captured.append({"host": host, "command": command, "timeout": timeout})
        return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

    return _fake


def test_send_aitbc_from_env_key_dry_run_by_default():
    result = json.loads(
        aitbc_mcp_mutating_tools.send_aitbc_from_env_key(
            key_env="FAUCET_PRIVATE_KEY",
            to_address=TO,
            amount="100",
        )
    )
    assert result.get("dry_run") is True
    assert "command" in result


def test_send_aitbc_from_env_key_requires_confirm():
    captured: list[dict[str, object]] = []
    with mock.patch.object(mcp_server, "_run_remote", _recorder(captured)):
        result = json.loads(
            aitbc_mcp_mutating_tools.send_aitbc_from_env_key(
                key_env="FAUCET_PRIVATE_KEY",
                to_address=TO,
                amount="100",
                dry_run=False,
                confirm=False,
            )
        )
    assert "Confirmation required" in result.get("error", "")
    assert not captured


def test_send_aitbc_from_env_key_executes_with_confirm():
    captured: list[dict[str, object]] = []
    with mock.patch.object(mcp_server, "_run_remote", _recorder(captured)):
        result = json.loads(
            aitbc_mcp_mutating_tools.send_aitbc_from_env_key(
                key_env="FAUCET_PRIVATE_KEY",
                to_address=TO,
                amount="100",
                fee="0.01",
                nonce_offset=2,
                dry_run=False,
                confirm=True,
                role="hub",
            )
        )
    assert result["returncode"] == 0
    assert len(captured) == 1
    cmd = str(captured[-1]["command"])
    assert "transactions send" in cmd
    assert "--key-env=FAUCET_PRIVATE_KEY" in cmd
    assert "--yes" in cmd
    assert f"--to={TO}" in cmd
    assert "--amount=100" in cmd
    assert "--fee=0.01" in cmd
    assert "--nonce-offset=2" in cmd
    # The env-key path must never smuggle a wallet selector.
    assert "--from" not in cmd


def test_send_aitbc_from_env_key_registered_on_server():
    """The tool is re-exported through aitbc_mcp_server like its siblings."""
    assert hasattr(mcp_server, "send_aitbc_from_env_key")
