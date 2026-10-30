"""ISLAND-LEAVE-STATUS-1 (#573): /rpc/islands/leave carries a machine-readable
code distinguishing "not a member" from "cannot leave the default island".

Before this change the manager returned a bare bool and both refusals
collapsed into one "(may not be a member)" message, which the CLI could not
branch on (test_swallow_edge.py had to keep not-a-member as an abort).
"""

from __future__ import annotations

from unittest.mock import patch

from aitbc_chain.network.island_manager import IslandManager
from aitbc_chain.rpc import islands as rpc_islands
from aitbc_chain.rpc.islands import LeaveIslandRequest, leave_island
import pytest


def _mgr() -> IslandManager:
    mgr = IslandManager("node-1", "default-island", "ait-hub")
    mgr.join_island("island-uuid-1", "island1", "ait-island1")
    return mgr


@pytest.mark.asyncio
async def test_leave_member_success():
    with patch.object(rpc_islands, "get_island_manager", return_value=_mgr()):
        resp = leave_island(LeaveIslandRequest(island_id="island-uuid-1"))
    assert resp.success is True
    assert resp.code == "left"
    assert resp.status == "left"


@pytest.mark.asyncio
async def test_leave_not_member_carries_code():
    with patch.object(rpc_islands, "get_island_manager", return_value=_mgr()):
        resp = leave_island(LeaveIslandRequest(island_id="island-never-joined"))
    assert resp.success is False
    assert resp.code == "not_member"
    assert "not a member" in resp.message.lower()


@pytest.mark.asyncio
async def test_leave_default_carries_code():
    with patch.object(rpc_islands, "get_island_manager", return_value=_mgr()):
        resp = leave_island(LeaveIslandRequest(island_id="default-island"))
    assert resp.success is False
    assert resp.code == "forbidden_default"
    assert "default island" in resp.message.lower()


@pytest.mark.asyncio
async def test_leave_codes_are_distinct():
    """Mutation guard: not_member and forbidden_default must not collapse."""
    mgr = _mgr()
    with patch.object(rpc_islands, "get_island_manager", return_value=mgr):
        not_member = leave_island(LeaveIslandRequest(island_id="island-never-joined"))
        forbidden = leave_island(LeaveIslandRequest(island_id="default-island"))
    assert not_member.code != forbidden.code
