"""Chain routes — list supported chains and get chain head."""

import os
from typing import Any

from fastapi import APIRouter

from aitbc.aitbc_logging import get_logger

from chain_client import DEFAULT_CHAIN, get_chain_head

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/chains")
def list_chains() -> dict[str, Any]:
    """List all supported chains"""
    chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
    return {
        "chains": [
            {"id": chain_id, "name": "AIT Hub Network", "status": "active"},
            {"id": "ait-mainnet", "name": "AIT Main Network", "status": "coming_soon"},
        ]
    }


@router.get("/api/chain/head")
async def api_chain_head(chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for chain head"""
    return await get_chain_head(chain_id)  # type: ignore[arg-type]
