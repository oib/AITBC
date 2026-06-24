#!/usr/bin/env python3
"""
AITBC Blockchain Explorer API
Agent-first API for blockchain data access
"""

import httpx
import uvicorn
from fastapi import FastAPI

from aitbc.aitbc_logging import configure_logging, get_logger

configure_logging(level="INFO", service_name="blockchain-explorer", to_file=True)
logger = get_logger(__name__)

from chain_client import BLOCKCHAIN_RPC_URLS, DEFAULT_CHAIN  # noqa: E402
from routers.analytics import router as analytics_router  # noqa: E402
from routers.blocks import router as blocks_router  # noqa: E402
from routers.chains import router as chains_router  # noqa: E402
from routers.export import router as export_router  # noqa: E402
from routers.search import router as search_router  # noqa: E402
from routers.transactions import router as transactions_router  # noqa: E402

app = FastAPI(title="AITBC Blockchain Explorer API", version="2.0.0")

app.include_router(chains_router)
app.include_router(analytics_router)
app.include_router(blocks_router)
app.include_router(transactions_router)
app.include_router(search_router)
app.include_router(export_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint"""
    try:
        # Test blockchain node connectivity
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN]}/rpc/head", timeout=5.0)
            node_status = "ok" if response.status_code == 200 else "error"
    except Exception:
        node_status = "error"

    return {
        "status": "ok" if node_status == "ok" else "degraded",
        "node_status": node_status,
        "version": "2.0.0",
        "features": "advanced_search,analytics,export,real_time",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
