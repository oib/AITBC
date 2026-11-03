"""Pin for MCP-READ-CLI-DENYLIST-GAPS-1 (#849).

``read_aitbc_cli`` now gates on an allowlist — ``GENERATED_READ_ONLY_AITBC_PATHS``,
emitted by the generator from the typed read tools — with the destructive
denylist kept as a veto. This test pins the gate against the generated
annotations themselves: every read_only_hint tool's path must be admitted,
every destructive_hint path refused, and the audit's two named leaks
(config get-secret, agent-staking verbs) refused.
"""

import sys
from pathlib import Path

import pytest

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server  # noqa: E402

TOOLS_READ = sorted(mcp_server.GENERATED_READ_ONLY_AITBC_PATHS)
TOOLS_DESTRUCTIVE = sorted(mcp_server.GENERATED_DESTRUCTIVE_AITBC_PATHS)


def _tokens(path_str):
    return path_str.split()[1:]


def test_allowlist_and_destructive_sets_are_sized():
    assert len(TOOLS_READ) > 50 and len(TOOLS_DESTRUCTIVE) > 300


@pytest.mark.parametrize("path", TOOLS_READ)
def test_read_only_paths_are_admitted(path):
    group, tokens = path.split()[0], _tokens(path)
    assert mcp_server._is_aitbc_subcommand_read_only(tokens or None, group, None), f"typed read tool path refused: {path}"


def test_denylist_veto_is_narrow():
    """The destructive denylist stays as a veto over the allowlist — today it
    over-gates the three typed read paths that carry a destructive denylist
    token (escrow/proposal/subscribe). The safe direction; if the set grows
    the collision wants a look, not silence."""
    vetoed = [p for p in TOOLS_READ if mcp_server._is_aitbc_subcommand_destructive(_tokens(p), p.split()[0], None)]
    assert vetoed == ["governance proposal show", "market escrow status", "messaging subscribe"]


@pytest.mark.parametrize("path", TOOLS_DESTRUCTIVE)
def test_destructive_paths_are_refused(path):
    group, tokens = path.split()[0], _tokens(path)
    assert not mcp_server._is_aitbc_subcommand_read_only(tokens or None, group, None), (
        f"destructive path slipped through the allowlist: {path}"
    )


@pytest.mark.parametrize(
    "group,tokens",
    [
        ("config", ["get-secret"]),
        ("agent-staking", ["claim"]),
        ("agent-staking", ["complete"]),
        ("agent-staking", ["distribute"]),
        ("agent-staking", ["unbond"]),
    ],
)
def test_audit_named_leaks_are_refused(group, tokens):
    assert not mcp_server._is_aitbc_subcommand_read_only(tokens, group, None)


def test_positional_args_still_admit_their_read_path():
    """account get takes a positional address — the read path is a prefix of
    the effective path, so args don't over-gate."""
    assert mcp_server._is_aitbc_subcommand_read_only(["get"], "account", ["0x" + "ab" * 20])
