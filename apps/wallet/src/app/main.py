from __future__ import annotations

import base64
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from aitbc import configure_logging, get_logger
from aitbc.rate_limiting import RateLimitMiddleware

from .api_jsonrpc import router as jsonrpc_router
from .api_rest import router as receipts_router
from .bridge import init_db, start_monitoring
from .settings import settings

configure_logging(level="INFO")
logger = get_logger(__name__)


async def _import_genesis_wallet_from_env() -> None:
    """Auto-import genesis wallet from node.env into daemon on startup if not already present."""
    import httpx

    node_env_file = os.getenv("AITBC_NODE_ENV_FILE", "/etc/aitbc/node.env")
    env = {}
    if os.path.exists(node_env_file):
        with open(node_env_file) as f:
            for line in f:
                line = line.strip()
                if line and (not line.startswith("#")) and ("=" in line):
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
                "metadata": {"address": address, "original_address": address, "chain_id": chain_id},
            }
            r = await client.post(f"{daemon_url}/v1/wallets", json=payload)
            if r.status_code in (200, 201):
                logger.info("Auto-imported genesis wallet: %s", address)
            elif r.status_code == 400 and "already exists" in r.text:
                pass
            else:
                logger.warning("Genesis wallet import failed: %s %s", r.status_code, r.text)
    except Exception as e:
        logger.warning("Could not auto-import genesis wallet: %s", e)


async def _import_file_wallets() -> None:
    """Auto-import wallets from wallet directory into daemon on startup."""
    import json
    from pathlib import Path

    import httpx

    wallet_dir = Path(os.getenv("WALLET_DIR", "/root/.aitbc/wallets"))
    if not wallet_dir.exists():
        return
    wallet_files = list(wallet_dir.glob("*.json"))
    if not wallet_files:
        return
    daemon_url = "http://localhost:8108"
    password = os.getenv("WALLET_IMPORT_PASSWORD", "Aitbc-Password-123")
    import asyncio

    max_retries = 10
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{daemon_url}/v1/wallets")
                existing = {w["wallet_id"] for w in r.json().get("items", [])}
                imported = 0
                for wallet_file in wallet_files:
                    try:
                        with open(wallet_file) as f:
                            data = json.load(f)
                        wallet_id = data.get("wallet_id") or wallet_file.stem
                        address = data.get("address", "")
                        private_key_hex = data.get("private_key", "").lstrip("0x")
                        chain_id = data.get("chain_id", "ait-hub.aitbc.bubuit.net")
                        if wallet_id in existing:
                            continue
                        if not private_key_hex:
                            continue
                        secret_b64 = base64.b64encode(bytes.fromhex(private_key_hex)).decode()
                        payload = {
                            "wallet_id": wallet_id,
                            "chain_id": chain_id,
                            "password": password,
                            "secret_key": secret_b64,
                            "metadata": {"address": address, "imported_from": str(wallet_file), "original_address": address},
                        }
                        r = await client.post(f"{daemon_url}/v1/wallets", json=payload)
                        if r.status_code in (200, 201):
                            imported += 1
                            logger.info("Auto-imported wallet: %s (%s)", wallet_id, address)
                    except Exception as e:
                        logger.warning("Failed to import wallet %s: %s", wallet_file.name, e)
                if imported > 0:
                    logger.info("Auto-imported %s wallet(s) from %s", imported, wallet_dir)
                return
        except httpx.ConnectError:
            if attempt < max_retries - 1:
                logger.info("Daemon not ready, retrying in %ss... (attempt %s/%s)", retry_delay, attempt + 1, max_retries)
                await asyncio.sleep(retry_delay)
            else:
                logger.warning("Could not auto-import file wallets: Daemon not ready after %s attempts", max_retries)
        except Exception as e:
            logger.warning("Could not auto-import file wallets: %s", e)
            return


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    init_db()
    start_monitoring()
    import asyncio

    asyncio.create_task(_import_genesis_wallet_from_env())
    asyncio.create_task(_import_file_wallets())
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(RateLimitMiddleware, rate=100, per=60)
    app.include_router(receipts_router, prefix="/v1")
    app.include_router(jsonrpc_router, prefix="/v1")
    from .bridge import router as bridge_router

    app.include_router(bridge_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "env": "dev", "python_version": "3.13.5"}

    return app


app = create_app()

if __name__ == "__main__":
    import os

    host = os.getenv("WALLET_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("WALLET_BIND_PORT", "8108"))

    uvicorn.run(app, host=host, port=port)
