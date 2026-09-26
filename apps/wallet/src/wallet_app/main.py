from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.async_tasks import create_task_with_logging
from aitbc.rate_limiting import RateLimitMiddleware

from .api_jsonrpc import router as jsonrpc_router
from .api_rest import router as receipts_router
from .bridge import init_db, start_monitoring, start_withdrawal_monitoring
from .settings import settings

configure_logging(level="INFO", service_name="wallet", to_file=True)
logger = get_logger(__name__)


def _daemon_auth_headers() -> dict[str, str]:
    """Headers for the daemon's own loopback calls to its REST API.

    Every /v1/wallets route is admin-gated, so these in-process bootstrap calls
    have to present the same key any other caller would. Returns empty when auth
    is switched off, which is the local-development case.
    """
    if not settings.auth_enabled or not settings.api_key:
        return {}
    return {"X-API-Key": settings.api_key}


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
    chain_id = env.get("CHAIN_ID", "ait-localnet")
    if not private_key_hex or not address:
        return
    daemon_url = "http://localhost:8108"
    password = os.getenv("WALLET_IMPORT_PASSWORD")
    if not password:
        logger.warning("WALLET_IMPORT_PASSWORD not set, skipping genesis wallet auto-import")
        return
    try:
        async with httpx.AsyncClient(timeout=5, headers=_daemon_auth_headers()) as client:
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

    wallet_dir = Path(os.getenv("WALLET_DIR") or os.getenv("AITBC_WALLET_DIR") or "/var/lib/aitbc/wallets")
    if not wallet_dir.exists():
        return
    wallet_files = list(wallet_dir.glob("*.json"))
    if not wallet_files:
        return
    daemon_url = "http://localhost:8108"
    keystore_password = os.getenv("WALLET_IMPORT_PASSWORD")
    if not keystore_password:
        logger.warning("WALLET_IMPORT_PASSWORD not set, skipping file wallet auto-import")
        return
    file_passwords = []
    for env_name in [
        "WALLET_FILE_PASSWORD",
        "AITBC_WALLET_PASSWORD",
        "WALLET_IMPORT_PASSWORD",
    ]:
        val = os.getenv(env_name)
        if val and val not in file_passwords:
            file_passwords.append(val)
    import asyncio

    max_retries = 10
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=5, headers=_daemon_auth_headers()) as client:
                r = await client.get(f"{daemon_url}/v1/wallets")
                existing = {w["wallet_id"] for w in r.json().get("items", [])}
                imported = 0
                for wallet_file in wallet_files:
                    try:
                        with open(wallet_file) as f:
                            data = json.load(f)
                        wallet_id = data.get("wallet_id") or wallet_file.stem
                        address = data.get("address", "")
                        raw_private_key = data.get("private_key", "")
                        if isinstance(raw_private_key, dict):
                            decrypted: str | None = None
                            for file_password in file_passwords:
                                try:
                                    from aitbc.security.encryption import decrypt_value

                                    decrypted = decrypt_value(raw_private_key, file_password)
                                    break
                                except Exception:
                                    continue
                            if decrypted is None:
                                logger.warning(
                                    "Skipping wallet %s: failed to decrypt private_key dict with any configured file password",
                                    wallet_file.name,
                                )
                                continue
                            raw_private_key = decrypted
                        if not isinstance(raw_private_key, str):
                            logger.warning(
                                "Skipping wallet %s: private_key field is not a string (got %s)",
                                wallet_file.name,
                                type(raw_private_key).__name__,
                            )
                            continue
                        # Strip a literal '0x'/'0X' prefix only. str.lstrip() treats its
                        # argument as a set of characters to strip, not a fixed prefix, so
                        # the previous .lstrip("0x") silently dropped any leading '0' or
                        # 'x' characters -- e.g. "0x00ab..." became "ab...", corrupting a
                        # key that legitimately starts with zero bytes.
                        private_key_hex = raw_private_key[2:] if raw_private_key[:2] in ("0x", "0X") else raw_private_key
                        chain_id = data.get("chain_id", "ait-localnet")
                        if wallet_id in existing:
                            continue
                        if not private_key_hex:
                            continue
                        secret_b64 = base64.b64encode(bytes.fromhex(private_key_hex)).decode()
                        payload = {
                            "wallet_id": wallet_id,
                            "chain_id": chain_id,
                            "password": keystore_password,
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


async def _operations_reconcile_loop() -> None:
    """Periodically expire stale pending operation rows.

    Wallet send operations use ``allow_adopt=False``, so expired leases become
    ``uncertain`` for operator resolution rather than silently re-driving a
    possibly-broadcast transaction.
    """
    from .api_rest import get_operations_ledger

    interval = int(os.getenv("WALLET_OPS_SWEEP_INTERVAL_SECONDS", "300"))
    while True:
        try:
            await get_operations_ledger().reconcile_async()
            await asyncio.to_thread(get_operations_ledger().purge)
        except Exception:
            logger.exception("Operation ledger reconciliation failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    init_db()
    start_monitoring()
    start_withdrawal_monitoring()

    create_task_with_logging(_import_genesis_wallet_from_env(), name="import_genesis_wallet")
    create_task_with_logging(_import_file_wallets(), name="import_file_wallets")
    create_task_with_logging(_operations_reconcile_loop(), name="operations_reconcile")
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
        import sys

        return {
            "status": "ok",
            "env": settings.app_env,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }

    @app.get("/ready")
    async def ready_check() -> Response:
        """Readiness probe — 503 while an enabled required feature is unavailable.

        Required: the keystore, wallet ledger and operation-ledger databases
        (all local sqlite, proving the data dir is writable and queryable) and
        the blockchain RPC the send/balance routes broadcast through. The
        coordinator URL is deliberately absent — it only serves receipt
        verification, which is not part of the wallet's required surface.
        """
        from aitbc.health_checks import run_readiness_checks

        checks = _wallet_readiness_checks()
        failed = await asyncio.to_thread(run_readiness_checks, checks)
        if failed:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "service": "wallet", "error": "readiness check failed", "failed": failed},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "service": "wallet", "checks": sorted(checks)},
        )

    return app


def _sqlite_check(path: object) -> Callable[[], None]:
    """A sqlite database at ``path`` opens and answers a trivial query."""
    import sqlite3

    def check() -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()

    return check


def _rpc_check() -> None:
    """The blockchain node's RPC answers /health — send and balance routes die without it."""
    import httpx

    resp = httpx.get(f"{settings.blockchain_rpc_url}/health", timeout=3.0)
    resp.raise_for_status()


def _wallet_readiness_checks() -> dict[str, Callable[[], None]]:
    from .api_rest import get_operations_ledger

    return {
        "keystore_db": _sqlite_check(settings.ledger_db_path.parent / "keystore.db"),
        "ledger_db": _sqlite_check(settings.ledger_db_path),
        "operations_db": _sqlite_check(get_operations_ledger().db_path),
        "blockchain_rpc": _rpc_check,
    }


app = create_app()

if __name__ == "__main__":
    import os

    # Default host is 127.0.0.1; override via WALLET_BIND_HOST for containers.
    host = os.getenv("WALLET_BIND_HOST", settings.host)
    port = int(os.getenv("WALLET_BIND_PORT", settings.port))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
