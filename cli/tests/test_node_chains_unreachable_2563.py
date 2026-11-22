"""#2563: `aitbc node chains` / `node chain list-chains` must not report
'No chains found' + exit 0 when every node is unreachable — failures go
to stderr, unreachable nodes are named in JSON, and all-down exits non-zero.
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.node.main as node_main
import aitbc_cli.core.node_client as node_client_mod
from aitbc_cli.commands.node import node


def _chain():
    return NS(
        id="chain-1",
        name="Side",
        type=NS(value="side"),
        purpose="testing",
        status=NS(value="active"),
        block_height=10,
        size_mb=1.0,
        privacy=NS(visibility="public"),
    )


@pytest.fixture
def nodes(monkeypatch):
    """Two configured nodes; ``scenario`` picks the collect_hosted_chains result."""
    scenario: dict = {"result": ([], [("n1", "refused"), ("n2", "refused")], 0)}

    async def fake_collect(nodes_arg, node_id=None):
        return scenario["result"]

    monkeypatch.setattr(node_main, "load_multichain_config", lambda: NS(nodes={"n1": object(), "n2": object()}))
    monkeypatch.setattr(node_main, "collect_hosted_chains", fake_collect)
    monkeypatch.setattr(node_client_mod, "collect_hosted_chains", fake_collect)
    import aitbc_cli.core.config as core_config

    monkeypatch.setattr(core_config, "load_multichain_config", lambda: NS(nodes={"n1": object(), "n2": object()}))
    return scenario


def test_all_nodes_down_exits_nonzero(nodes):
    r = CliRunner().invoke(node, ["chains"], obj={"output": "table"})
    assert r.exit_code != 0
    assert "No chains found" in r.output
    # per-node errors belong on stderr, not stdout
    assert "Error getting chains from node n1" in r.stderr
    assert "Error getting chains" not in r.stdout


def test_partial_failure_marks_unreachable_in_json(nodes):
    nodes["result"] = ([("n2", _chain())], [("n1", "refused")], 1)
    r = CliRunner().invoke(node, ["chains"], obj={"output": "json"})
    assert r.exit_code == 0, r.output
    doc = json.loads(r.stdout)
    assert doc["unreachable_nodes"] == ["n1"]
    assert doc["chains"][0]["Chain ID"] == "chain-1"


def test_all_answered_empty_still_exit_zero(nodes):
    nodes["result"] = ([], [], 2)
    r = CliRunner().invoke(node, ["chains"], obj={"output": "table"})
    assert r.exit_code == 0
    assert "No chains found" in r.output


def test_chain_list_chains_all_down_exits_nonzero(nodes):
    r = CliRunner().invoke(node, ["chain", "list-chains"], obj={"output": "table"})
    assert r.exit_code != 0
    assert "No chains found" in r.output
