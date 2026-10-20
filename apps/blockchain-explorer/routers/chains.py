"""Chain routes — list supported chains and get chain head."""

from aitbc.utils.chain_id import ChainIdNotConfigured, resolve_chain_id
from typing import Any

from fastapi import APIRouter

from aitbc.aitbc_logging import get_logger

from chain_client import get_chain_head

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/chains")
def list_chains() -> dict[str, Any]:
    """List all supported chains"""
    try:
        local_id = resolve_chain_id()
        local = {"id": local_id, "name": "AIT Hub Network", "status": "active"}
    except ChainIdNotConfigured:
        local = {"id": "unconfigured", "name": "AIT Hub Network", "status": "unconfigured"}
    return {"chains": [local]}


@router.get("/api/chain/head")
async def api_chain_head(chain_id: str | None = None) -> dict[str, Any]:
    """API endpoint for chain head"""
    return await get_chain_head(chain_id)
