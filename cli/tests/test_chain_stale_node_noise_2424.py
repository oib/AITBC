"""#2424: unreachable multichain registry nodes are classified once, not
spammed per call — residual of #2408's stale-node noise report."""

import asyncio
import logging
from types import SimpleNamespace as NS
from typing import Any, cast

import pytest

import aitbc_cli.core.chain_manager as cm
from aitbc_cli.core.chain_manager import ChainManager


def _mgr(node_ids: list[str]) -> ChainManager:
    mgr = ChainManager.__new__(ChainManager)
    mgr.config = cast(Any, NS(nodes={nid: NS() for nid in node_ids}))
    mgr._chain_cache = {}
    mgr._node_clients = {}
    return mgr


def _chain(cid: str = "bc-2") -> Any:
    return NS(
        id=cid,
        type=NS(value="main"),
        privacy=NS(visibility="public"),
        size_mb=1.0,
        node_count=1,
    )


def test_partial_failure_logs_one_summary_not_per_node_errors(caplog):
    mgr = _mgr(["dead-a", "dead-b", "live"])

    async def fake_get(node_id):
        if node_id == "live":
            return [_chain()]
        raise ConnectionError("All connection attempts failed")

    mgr._get_node_chains = fake_get  # type: ignore[method-assign]
    with caplog.at_level(logging.DEBUG):
        chains = asyncio.run(mgr.list_chains())

    assert [c.id for c in chains] == ["bc-2"]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == [], f"per-node error spam: {[r.getMessage() for r in errors]}"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Skipped 2 configured node(s)" in w for w in warnings)


def test_all_nodes_fail_still_raises():
    mgr = _mgr(["dead-a", "dead-b"])

    async def dead(node_id):
        raise ConnectionError("refused")

    mgr._get_node_chains = dead  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="All nodes failed"):
        asyncio.run(mgr.list_chains())


def test_get_node_chains_propagates_for_fanout_classification():
    """_get_node_chains must raise so callers can classify — the old
    error-log + `return []` swallow hid failures from the all-nodes check."""

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_hosted_chains(self):
            raise ConnectionError("All connection attempts failed")

    mgr = _mgr(["dead"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cm, "NodeClient", lambda cfg: _Client())
        with pytest.raises(ConnectionError):
            asyncio.run(mgr._get_node_chains("dead"))
