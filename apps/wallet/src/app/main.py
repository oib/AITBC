from __future__ import annotations

import base64
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from aitbc.rate_limiting import RateLimitMiddleware

from .api_jsonrpc import router as jsonrpc_router
from .api_rest import router as receipts_router
from .settings import settings

logger = logging.getLogger(__name__)


async def _import_genesis_wallet_from_env():
    """Auto-import genesis wallet from node.env into daemon on startup if not already present."""
    import httpx

    node_env_file = os.getenv("AITBC_NODE_ENV_FILE", "/etc/aitbc/node.env")
    env = {}
    if os.path.exists(node_env_file):
        with open(node_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    private_key_hex = env.get("GENESIS_PRIVATE_KEY", "")
    address = env.get("GENESIS_ADDRESS", "")
    chain_id = env.get("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    if not private_key_hex or not address:
        return

    daemon_url = "http://localhost:8108"
    password = os.getenv("WALLET_IMPORT_PASSWORD", "Aitbc-Import-Pass1")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # Check if already imported
            r = await client.get(f"{daemon_url}/v1/wallets")
            existing = {w["wallet_id"] for w in r.json().get("items", [])}
            if "genesis" in existing:
                return

            secret_b64 = base64.b64encode(bytes.fromhex(private_key_hex)).decode()
            payload = {
                "wallet_id": "genesis",
                "chain_id": chain_id,
                "password": password,
                "secret_key": secret_b64,
                "metadata": {
                    "address": address,
                    "original_address": address,
                    "chain_id": chain_id,
                }
            }
            r = await client.post(f"{daemon_url}/v1/wallets", json=payload)
            if r.status_code in (200, 201):
                logger.info(f"Auto-imported genesis wallet: {address}")
            elif r.status_code == 400 and "already exists" in r.text:
                pass
            else:
                logger.warning(f"Genesis wallet import failed: {r.status_code} {r.text}")
    except Exception as e:
        logger.warning(f"Could not auto-import genesis wallet: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _import_genesis_wallet_from_env()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    # Add rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        rate=100,
        per=60
    )

    app.include_router(receipts_router, prefix="/v1")
    app.include_router(jsonrpc_router, prefix="/v1")

    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "env": "dev",
            "python_version": "3.13.5"
        }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8108)
