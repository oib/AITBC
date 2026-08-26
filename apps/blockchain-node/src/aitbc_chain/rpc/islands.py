"""
Island-related RPC endpoints.
"""

import json
import os
import socket
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from ..config import settings
from ..logger import get_logger
from ..network.island_manager import get_island_manager

_logger = get_logger(__name__)


class JoinIslandRequest(BaseModel):
    """Request model for joining an island"""

    island_id: str
    island_name: str
    chain_id: str | list[str]
    role: str = "compute-provider"
    is_hub: bool = False


class JoinIslandResponse(BaseModel):
    """Response model for joining an island"""

    success: bool
    island_id: str
    island_name: str
    island_chain_id: str
    status: str
    message: str
    credentials: dict[str, Any]
    members: list[dict[str, Any]]


class LeaveIslandRequest(BaseModel):
    """Request model for leaving an island"""

    island_id: str


class LeaveIslandResponse(BaseModel):
    """Response model for leaving an island"""

    success: bool
    island_id: str
    status: str
    message: str


class BridgeRequestRequest(BaseModel):
    """Request model for requesting a bridge"""

    target_island_id: str


class BridgeRequestResponse(BaseModel):
    """Response model for bridge request"""

    success: bool
    request_id: str
    target_island_id: str
    status: str
    message: str


def _build_join_credentials(island_id: str, island_name: str, island_chain_id: str) -> dict[str, Any]:
    """Build the credentials block returned to a joining node."""
    hub_host = settings.hub_discovery_url or socket.gethostname()
    public_rpc = os.getenv("RPC_PUBLIC_ENDPOINT", f"http://{hub_host}/rpc")
    credentials: dict[str, Any] = {
        "chain_id": island_chain_id,
        "island_id": island_id,
        "island_name": island_name,
        "rpc_endpoint": public_rpc,
    }

    # Optionally include genesis metadata if we can find a local genesis file.
    data_dir = Path("/var/lib/aitbc/data")
    genesis_candidates = [
        data_dir / settings.chain_id / "genesis.json",
        data_dir / island_chain_id / "genesis.json",
        data_dir / "genesis.json",
    ]
    for genesis_path in genesis_candidates:
        if genesis_path.exists():
            try:
                with open(genesis_path) as f:
                    genesis_data = json.load(f)
                blocks = genesis_data.get("blocks", [])
                if blocks:
                    credentials["genesis_block_hash"] = blocks[0].get("hash", "")
            except (OSError, json.JSONDecodeError):
                pass
            break

    keystore_path = Path("/var/lib/aitbc/keystore/validator_keys.json")
    if keystore_path.exists():
        try:
            with open(keystore_path) as f:
                keys = json.load(f)
            for key_id in keys:
                credentials["genesis_address"] = key_id
                break
        except (OSError, json.JSONDecodeError):
            pass

    return credentials


def _island_members(island_manager: Any, island_id: str) -> list[dict[str, Any]]:
    """Return known members of an island as simple dicts."""
    members: list[dict[str, Any]] = []
    island = island_manager.get_island_info(island_id)
    if island is not None and island.is_hub:
        members.append(
            {
                "node_id": island_manager.local_node_id,
                "is_hub": True,
                "address": "127.0.0.1",
                "port": 7070,
            }
        )
    for peer_id in island_manager.island_peers.get(island_id, set()):
        members.append({"node_id": peer_id, "is_hub": False})
    return members


async def join_island(request: JoinIslandRequest) -> JoinIslandResponse:
    """
    Join an island for edge compute operations.
    Calls IslandManager.join_island to register the node as a member of the specified island.
    Returns full island credentials and is idempotent: if the island is already joined,
    success is still true and the response contains the existing membership details.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")

    # Idempotent join: try to register, but still return the island info if already a member.
    joined = island_manager.join_island(
        island_id=request.island_id, island_name=request.island_name, chain_id=request.chain_id, is_hub=request.is_hub
    )

    island = island_manager.get_island_info(request.island_id)
    if island is None:
        # The join failed and the island is unknown.
        return JoinIslandResponse(
            success=False,
            island_id=request.island_id,
            island_name=request.island_name,
            island_chain_id=request.island_id,
            status="failed",
            message=f"Island {request.island_id} is not known on this hub",
            credentials={},
            members=[],
        )

    chain_id = island.chain_id or (request.chain_id if isinstance(request.chain_id, str) else request.chain_id[0])
    credentials = _build_join_credentials(island.island_id, island.island_name, chain_id)
    members = _island_members(island_manager, island.island_id)

    status = "joined" if joined else "already_member"
    message = (
        f"Successfully joined island {island.island_name}" if joined else f"Already a member of island {island.island_name}"
    )

    return JoinIslandResponse(
        success=True,
        island_id=island.island_id,
        island_name=island.island_name,
        island_chain_id=chain_id,
        status=status,
        message=message,
        credentials=credentials,
        members=members,
    )


async def leave_island(request: LeaveIslandRequest) -> LeaveIslandResponse:
    """
    Leave an island.
    Calls IslandManager.leave_island to remove the node from the specified island.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")

    success = island_manager.leave_island(request.island_id)

    if success:
        return LeaveIslandResponse(
            success=True, island_id=request.island_id, status="left", message=f"Successfully left island {request.island_id}"
        )
    else:
        return LeaveIslandResponse(
            success=False,
            island_id=request.island_id,
            status="failed",
            message=f"Failed to leave island {request.island_id} (may not be a member)",
        )


async def list_islands() -> dict[str, Any]:
    """
    List all islands that the node is a member of.
    Calls IslandManager.get_all_islands to retrieve island memberships.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")

    islands = island_manager.get_all_islands()

    return {
        "islands": [
            {
                "island_id": island.island_id,
                "island_name": island.island_name,
                "chain_id": island.chain_id,
                "chain_ids": island.chain_ids,
                "status": island.status.value,
                "role": getattr(island, "role", "unknown"),
                "peer_count": island.peer_count,
                "is_hub": island.is_hub,
                "joined_at": island.joined_at,
            }
            for island in islands
        ],
        "total": len(islands),
    }


async def get_island(island_id: str) -> dict[str, Any]:
    """
    Get details about a specific island.
    Calls IslandManager.get_island_info to retrieve island membership details.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")

    island = island_manager.get_island_info(island_id)

    if island is None:
        raise HTTPException(status_code=404, detail=f"Island {island_id} not found")

    return {
        "island_id": island.island_id,
        "island_name": island.island_name,
        "chain_id": island.chain_id,
        "chain_ids": island.chain_ids,
        "status": island.status.value,
        "role": getattr(island, "role", "unknown"),
        "peer_count": island.peer_count,
        "is_hub": island.is_hub,
        "joined_at": island.joined_at,
    }


async def request_bridge(request: BridgeRequestRequest) -> BridgeRequestResponse:
    """
    Request a bridge to another island for cross-island communication.
    Calls IslandManager.request_bridge to initiate a bridge request.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")

    request_id = island_manager.request_bridge(request.target_island_id)

    if request_id:
        return BridgeRequestResponse(
            success=True,
            request_id=request_id,
            target_island_id=request.target_island_id,
            status="pending",
            message=f"Bridge request {request_id} submitted for {request.target_island_id}",
        )
    else:
        return BridgeRequestResponse(
            success=False,
            request_id="",
            target_island_id=request.target_island_id,
            status="failed",
            message=f"Failed to request bridge to {request.target_island_id} (may already be a member)",
        )
