"""CLI-EXIT-TRUTH-1: blockchain list must exit non-zero when all nodes fail."""

import asyncio
from types import SimpleNamespace as NS
from typing import Any, cast
from unittest.mock import AsyncMock

import aitbc_cli.core.chain_manager as cm


def _mgr(mocker: Any) -> Any:
    mgr = cm.ChainManager.__new__(cm.ChainManager)
    mgr.config = cast(Any, NS(nodes={"n1": NS(), "n2": NS()}))
    mgr._chain_cache = {}
    return mgr


def test_all_nodes_fail_raises(mocker: Any) -> None:
    mgr = _mgr(mocker)
    mocker.patch.object(mgr, "_get_node_chains", new=AsyncMock(side_effect=ConnectionError("refused")))
    try:
        asyncio.run(mgr.list_chains())
        raise AssertionError("should have raised")
    except ConnectionError:
        pass


def test_one_node_succeeds_ok(mocker: Any) -> None:
    mgr = _mgr(mocker)
    chain = NS(id="c", type=NS(value="main"), privacy=NS(visibility="public"), size_mb=1.0, node_count=1)

    async def mixed(node_id: str) -> list:
        if node_id == "n1":
            raise ConnectionError("refused")
        return [chain]

    mocker.patch.object(mgr, "_get_node_chains", new=mixed)
    assert len(asyncio.run(mgr.list_chains())) == 1
