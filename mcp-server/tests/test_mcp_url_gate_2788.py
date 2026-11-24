"""AUDIT-EDGE pin: #2788 — URL-retarget options are mutation-class.

Read gates never inspected option VALUES or URL-retarget flags, so a
read_only_hint tool could be aimed at an attacker host while the node's
stored JWT / X-API-Key / RPC key still attached (credential exfil + SSRF).
*_url option keys are now refused on every no-confirm read path and force
confirm on run_aitbc_cli.
"""

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_cli_helpers as helpers  # noqa: E402
import aitbc_mcp_server as mcp_server  # noqa: E402


def _suggests(key: str) -> bool:
    return helpers._options_suggest_mutation({key: "https://attacker.example"})


def test_url_option_keys_are_mutation_class() -> None:
    for key in ("coordinator-url", "coordinator_url", "rpc-url", "rpc_url", "node-url", "url", "market-urls"):
        assert _suggests(key), f"{key} must be treated as mutation-class"


def test_innocent_option_keys_still_pass() -> None:
    for key in ("mine", "limit", "format", "curl", "curling"):
        assert not _suggests(key), f"{key} must not be flagged"


def test_read_tool_helper_refuses_url_retarget() -> None:
    out = json.loads(
        mcp_server._aitbc_cli_read_tool(
            None,
            None,
            "wallet",
            subcommand=["list"],
            options={"coordinator-url": "https://attacker.example"},
        )
    )
    assert "error" in out
    assert "mutating" in out["error"]


def test_read_aitbc_cli_refuses_url_retarget() -> None:
    import aitbc_mcp_cli_pivot_tools as pivot

    out = json.loads(
        pivot.read_aitbc_cli(
            group="wallet",
            subcommand=["list"],
            options={"rpc-url": "https://attacker.example"},
        )
    )
    assert "error" in out
