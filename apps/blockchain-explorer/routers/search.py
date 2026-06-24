"""Search routes — advanced transaction and block search via data layer or RPC."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger

from chain_client import BLOCKCHAIN_RPC_URLS, DEFAULT_CHAIN, USE_DATA_LAYER, get_data_layer

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/search/transactions")
async def search_transactions(
    address: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    tx_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = DEFAULT_CHAIN,
) -> dict[str, Any]:
    """Advanced transaction search"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            result = await data_layer.get_transactions(
                address, amount_min, amount_max, tx_type, since, until, limit, offset, chain_id, rpc_url
            )
            return result if isinstance(result, dict) else {"transactions": result}
        else:
            # Original implementation without data layer
            # Build query parameters
            params: dict[str, str | int | float] = {}
            if address:
                params["address"] = address
            if amount_min:
                params["amount_min"] = amount_min
            if amount_max:
                params["amount_max"] = amount_max
            if tx_type:
                params["type"] = tx_type
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            params["limit"] = limit
            params["offset"] = offset
            params["chain_id"] = chain_id if chain_id else DEFAULT_CHAIN

            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/search/transactions", params=params)
                if response.status_code == 200:
                    result = response.json()
                    return result if isinstance(result, dict) else {"transactions": result}
                elif response.status_code == 404:
                    return {"transactions": []}
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch transactions from blockchain RPC: {response.text}",
                    )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain RPC unavailable: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/api/search/blocks")
async def search_blocks(
    validator: str | None = None,
    since: str | None = None,
    until: str | None = None,
    min_tx: int | None = None,
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = DEFAULT_CHAIN,
) -> dict[str, Any]:
    """Advanced block search"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            result = await data_layer.get_blocks(validator, since, until, min_tx, limit, offset, chain_id, rpc_url)
            return result if isinstance(result, dict) else {"blocks": result}
        else:
            # Original implementation without data layer
            params: dict[str, str | int] = {}
            if validator:
                params["validator"] = validator
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            if min_tx:
                params["min_tx"] = min_tx
            params["limit"] = limit
            params["offset"] = offset
            params["chain_id"] = chain_id if chain_id else DEFAULT_CHAIN

            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/search/blocks", params=params)
                if response.status_code == 200:
                    result = response.json()
                    return result if isinstance(result, dict) else {"blocks": result}
                elif response.status_code == 404:
                    return {"blocks": []}
                else:
                    raise HTTPException(
                        status_code=response.status_code, detail=f"Failed to fetch blocks from blockchain RPC: {response.text}"
                    )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain RPC unavailable: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e
