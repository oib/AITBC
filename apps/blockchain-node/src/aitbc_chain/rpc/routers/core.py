"""
Core blockchain router.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ...config import settings
from ...database import session_scope
from ...logger import get_logger
from ...models import Account, Transaction
from ..accounts import (
    create_account,
    faucet_request,
    get_account,
    get_account_alias,
    get_balance_breakdown,
    get_state_delta,
    get_state_snapshot,
    reconcile_balance,
)
from ..blocks import get_block, get_blocks_range, get_genesis_allocations, get_head, import_block
from ..chains import ChainActionRequest, ChainActionResponse, list_chains, start_chain, stop_chain
from ..gossip import GetLogsRequest, GetLogsResponse, get_logs
from ..sync import export_chain, force_sync, get_sync_config, import_chain
from ..transactions import (
    TransactionRequest,
    query_transactions,
    submit_marketplace_transaction,
    submit_transaction,
)
from ..utils import get_chain_id

_logger = get_logger(__name__)

router = APIRouter(tags=["core"])


@router.get("/genesis_allocations", summary="Get genesis allocations from blockchain")
@rate_limit(rate=200, per=60)
async def get_genesis_allocations_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get genesis allocations from genesis block metadata for RPC bootstrap"""
    return await get_genesis_allocations(request, chain_id)  # type: ignore[no-any-return]


@router.get("/chain/head", summary="Get current chain head (compatibility alias)")
@rate_limit(rate=200, per=60)
async def get_chain_head_alias_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get current chain head (alias for /head). Logs caller to identify stale clients."""
    _logger.info(
        "Chain head alias called: path=%s client=%s user_agent=%s",
        request.url.path,
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent", "unknown"),
    )
    return await get_head(request, chain_id)  # type: ignore[no-any-return]


@router.get("/head", summary="Get current chain head")
@rate_limit(rate=200, per=60)
async def get_head_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get current chain head"""
    return await get_head(request, chain_id)  # type: ignore[no-any-return]


@router.get("/height", summary="Get current chain height")
@rate_limit(rate=200, per=60)
async def get_height_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get current chain height"""
    head = await get_head(request, chain_id)
    return {"height": head.get("height", 0)}


@router.get("/blocks/{height}", summary="Get block by height")
@rate_limit(rate=200, per=60)
async def get_block_route(request: Request, height: int, chain_id: str | None = None) -> dict[str, Any]:
    """Get block by height"""
    return await get_block(request, height, chain_id)  # type: ignore[no-any-return]


def _log_legacy_block_caller(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    x_forwarded = request.headers.get("x-forwarded-for", "")
    if x_forwarded:
        client_host = x_forwarded.split(",")[0].strip() or client_host
    user_agent = request.headers.get("user-agent", "unknown")
    _logger.info(
        "Legacy /rpc/block called by %s (UA: %s) path=%s",
        client_host,
        user_agent,
        request.url.path,
    )


@router.get("/block", summary="Get a block (head by default, or by query height)")
@rate_limit(rate=200, per=60)
async def get_block_alias_route(request: Request, height: int | None = None, chain_id: str | None = None) -> dict[str, Any]:
    """Get the head block, or a specific block if height is provided."""
    _log_legacy_block_caller(request)
    if height is None:
        head = await get_head(request, chain_id)
        height = head.get("height", 0)
    return await get_block(request, height, chain_id)  # type: ignore[no-any-return]


@router.get("/block/{height}", summary="Get block by height (singular alias)")
@rate_limit(rate=200, per=60)
async def get_block_path_alias_route(request: Request, height: int, chain_id: str | None = None) -> dict[str, Any]:
    """Get block by height (singular alias for /blocks/{height})."""
    _log_legacy_block_caller(request)
    return await get_block(request, height, chain_id)  # type: ignore[no-any-return]


@router.get("/blocks-range", summary="Get blocks in height range")
@rate_limit(rate=200, per=60)
async def get_blocks_range_route(
    request: Request,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
    include_tx: bool = True,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """Get blocks in a height range.

    Either specify ``start`` and ``end`` (inclusive height range), or
    ``limit`` (returns the most recent N blocks from the chain head).
    If neither is provided, defaults to start=0, end=10.
    """
    if limit is not None and start is None and end is None:
        # Resolve the current head and compute the range
        from ..blocks import get_head

        head_result = await get_head(request, chain_id)
        head_height = head_result.get("height", 0)
        end = head_height
        start = max(0, head_height - limit + 1)
    else:
        start = start or 0
        end = end if end is not None else 10
    return await get_blocks_range(request, start, end, include_tx, chain_id)  # type: ignore[no-any-return]


@router.get("/info", summary="Get blockchain information")
@rate_limit(rate=200, per=60)
async def get_info_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get comprehensive blockchain information including transactions, accounts, and genesis parameters"""
    head = await get_head(request, chain_id)
    resolved_chain_id = get_chain_id(chain_id)

    with session_scope(resolved_chain_id) as session:
        total_transactions = session.exec(
            select(func.count()).select_from(Transaction).where(Transaction.chain_id == resolved_chain_id)
        ).one()
        total_accounts = session.exec(
            select(func.count()).select_from(Account).where(Account.chain_id == resolved_chain_id)
        ).one()

    # Use the actual settings fields; there is no difficulty in PoA, so omit it.
    genesis_params = {
        "block_time_seconds": settings.block_time_seconds,
        "max_block_size_bytes": settings.max_block_size_bytes,
    }

    return {
        "chain_id": getattr(settings, "chain_id", "ait-hub.aitbc.bubuit.net"),
        "height": head.get("height", 0),
        "total_transactions": total_transactions,
        "total_accounts": total_accounts,
        "genesis_params": genesis_params,
        "last_block_hash": head.get("hash", ""),
        "timestamp": head.get("timestamp", datetime.now(UTC).isoformat()),
    }


@router.get("/status", summary="Get node status (alias for /info)")
@rate_limit(rate=200, per=60)
async def get_status_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get node status - alias for /info endpoint"""
    return await get_info_route(request, chain_id)  # type: ignore[no-any-return]


@router.get("/network-info", summary="Get network information for joining")
@rate_limit(rate=100, per=60)
async def get_network_info_route(request: Request) -> dict[str, Any]:
    """Get network configuration information for open island joining"""
    import os
    import socket
    from pathlib import Path

    env_file = Path("/etc/aitbc/blockchain.env")
    p2p_host = os.getenv("p2p_bind_host", "0.0.0.0")  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    p2p_port = os.getenv("p2p_bind_port", "8200")
    p2p_node_id = os.getenv("p2p_node_id", "unknown")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("p2p_bind_host="):
                    p2p_host = line.split("=", 1)[1]
                elif line.startswith("p2p_bind_port="):
                    p2p_port = line.split("=", 1)[1]
                elif line.startswith("p2p_node_id="):
                    p2p_node_id = line.split("=", 1)[1]
    hostname = os.getenv("AITBC_HOSTNAME", socket.gethostname())
    p2p_endpoint = f"{hostname}:{p2p_port}" if p2p_host == "0.0.0.0" else f"{p2p_host}:{p2p_port}"  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    chain_id = getattr(settings, "chain_id", "ait-hub.aitbc.bubuit.net")
    supported_chains = getattr(settings, "supported_chains", "ait-mainnet").split(",")
    protocol = os.getenv("AITBC_PROTOCOL", "http")
    if request.url.scheme:
        protocol = request.url.scheme
    contact_email = os.getenv("CONTACT_EMAIL", "andreas.fleckl@bubuit.net")
    rpc_endpoint = f"{protocol}://{hostname}/rpc"
    return {
        "p2p_endpoint": p2p_endpoint,
        "p2p_node_id": p2p_node_id,
        "chain_id": chain_id,
        "network_type": "open_island",
        "supported_chains": supported_chains,
        "connection_instructions": f"Set default_peer_rpc_url={rpc_endpoint} and enable subscription (subscription_enabled=true, subscription_transport=websocket). Blocks are pushed via WebSocket to {rpc_endpoint}/subscribe/ws",
        "rpc_endpoint": rpc_endpoint,
        "api_gateway": f"{protocol}://{hostname}/api",
        "contact_email": contact_email,
        "version": "0.5.4",
    }


@router.post("/importBlock", summary="Import a block")
@rate_limit(rate=50, per=60)
async def import_block_route(request: Request, block_data: dict) -> dict[str, Any]:
    """Import a block into the blockchain"""
    return await import_block(request, block_data)  # type: ignore[no-any-return]


@router.post("/transaction", summary="Submit transaction")
@rate_limit(rate=50, per=60)
async def submit_transaction_route(request: Request, tx_data: TransactionRequest) -> dict[str, Any]:
    """Submit a new transaction to the mempool"""
    return await submit_transaction(request, tx_data)  # type: ignore[no-any-return]


@router.get("/mempool", summary="Get pending transactions")
@rate_limit(rate=200, per=60)
async def get_mempool_api_route(request: Request, chain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get pending transactions from mempool"""
    # Import locally to avoid circular dependency
    from ..transactions import get_mempool

    return await get_mempool(request, chain_id, limit)  # type: ignore[no-any-return]


@router.post("/transactions/marketplace", summary="Submit marketplace transaction")
@rate_limit(rate=50, per=60)
async def submit_marketplace_transaction_route(request: Request, tx_data: dict[str, Any]) -> dict[str, Any]:
    """Submit a marketplace transaction"""
    return await submit_marketplace_transaction(request, tx_data)  # type: ignore[no-any-return]


@router.get("/transactions", summary="Query transactions")
@rate_limit(rate=200, per=60)
async def query_transactions_route(
    request: Request,
    transaction_type: str | None = None,
    island_id: str | None = None,
    pair: str | None = None,
    status: str | None = None,
    order_id: str | None = None,
    limit: int | None = 100,
    chain_id: str | None = None,
    address: str | None = None,
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query transactions with optional filters"""
    return await query_transactions(
        request, transaction_type, island_id, pair, status, order_id, limit, chain_id, address, job_id
    )  # type: ignore[no-any-return]


@router.get("/transaction/{tx_hash}", summary="Get one transaction by hash")
@rate_limit(rate=200, per=60)
async def get_transaction_route(request: Request, tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """Look up a single transaction by hash; 404 when the chain does not have it."""
    from ..transactions import get_transaction

    return await get_transaction(request, tx_hash, chain_id)  # type: ignore[no-any-return]


@router.get("/account/{address}", summary="Get account information")
@rate_limit(rate=200, per=60)
async def get_account_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information"""
    return await get_account(request, address, chain_id)  # type: ignore[no-any-return]


@router.get("/accounts/{address}", summary="Get account information (alias)")
@rate_limit(rate=200, per=60)
async def get_account_alias_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information (alias endpoint)"""
    return await get_account_alias(request, address, chain_id)  # type: ignore[no-any-return]


@router.get("/state/snapshot", summary="Get full account state snapshot")
@rate_limit(rate=10, per=60)
async def get_state_snapshot_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Return all accounts and the computed state root for follower state sync."""
    return await get_state_snapshot(request, chain_id)


@router.get("/state/delta", summary="Get state delta between two heights")
@rate_limit(rate=10, per=60)
async def get_state_delta_route(
    request: Request, from_height: int, to_height: int, chain_id: str | None = None
) -> dict[str, Any]:
    """Return state diff for delta sync — only changed accounts."""
    return await get_state_delta(request, from_height, to_height, chain_id)


@router.post("/register-account", summary="Create/register a new account on the blockchain")
@rate_limit(rate=100, per=60)
async def create_account_route(request: Request, account_data: dict) -> dict[str, Any]:
    """Create or register a new account on the blockchain"""
    return await create_account(request, account_data)  # type: ignore[no-any-return]


@router.post("/faucet", summary="Request test tokens from faucet")
@rate_limit(rate=10, per=3600)
async def faucet_request_route(request: Request, faucet_data: dict) -> dict[str, Any]:
    """Request test tokens from the blockchain faucet"""
    return await faucet_request(request, faucet_data)  # type: ignore[no-any-return]


@router.get("/balance/{address}", summary="Get detailed balance breakdown")
@rate_limit(rate=100, per=60)
async def get_balance_breakdown_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get detailed balance breakdown"""
    return await get_balance_breakdown(request, address, chain_id)  # type: ignore[no-any-return]


@router.get("/balance/{address}/reconcile", summary="Reconcile balance")
@rate_limit(rate=20, per=60)
async def reconcile_balance_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Reconcile account balance against all recorded operations"""
    return await reconcile_balance(request, address, chain_id)  # type: ignore[no-any-return]


@router.get("/export-chain", summary="Export full chain state")
@rate_limit(rate=200, per=60)
async def export_chain_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Export full chain state as JSON for manual synchronization"""
    return await export_chain(request, chain_id)  # type: ignore[no-any-return]


@router.post("/import-chain", summary="Import chain state")
@rate_limit(rate=50, per=60)
async def import_chain_route(request: Request, import_data: dict) -> dict[str, Any]:
    """Import chain state from JSON for manual synchronization"""
    return await import_chain(request, import_data)  # type: ignore[no-any-return]


@router.post("/force-sync", summary="Force reorg to specified peer")
@rate_limit(rate=50, per=60)
async def force_sync_route(request: Request, peer_data: dict) -> dict[str, Any]:
    """Force blockchain reorganization to sync with specified peer"""
    return await force_sync(request, peer_data)  # type: ignore[no-any-return]


@router.get("/sync/config", summary="Get sync optimization configuration (v0.6.2)")
@rate_limit(rate=200, per=60)
async def get_sync_config_route(request: Request) -> dict[str, Any]:
    """Get sync optimization configuration"""
    return await get_sync_config(request)  # type: ignore[no-any-return]


@router.post("/eth_getLogs", summary="Query smart contract event logs")
@rate_limit(rate=200, per=60)
async def get_logs_route(request: Request, logs_request: GetLogsRequest, chain_id: str | None = None) -> GetLogsResponse:
    """Query smart contract event logs using eth_getLogs-compatible endpoint"""
    return await get_logs(request, logs_request, chain_id)  # type: ignore[no-any-return]


@router.post("/chains/start", summary="Start a secondary chain (v0.6.4)")
async def start_chain_route(request: ChainActionRequest) -> ChainActionResponse:
    """Start a secondary chain instance via MultiChainManager"""
    return await start_chain(request)


@router.post("/chains/stop", summary="Stop a secondary chain (v0.6.4)")
async def stop_chain_route(request: ChainActionRequest) -> ChainActionResponse:
    """Stop a secondary chain instance via MultiChainManager"""
    return await stop_chain(request)


@router.get("/chains", summary="List all chain instances (v0.6.4)")
@rate_limit(rate=100, per=60)
async def list_chains_route() -> dict[str, Any]:
    """List all chain instances managed by the MultiChainManager"""
    return await list_chains()
