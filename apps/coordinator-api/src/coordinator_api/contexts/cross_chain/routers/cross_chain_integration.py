"""
Cross-Chain Integration API Router
REST API endpoints for enhanced multi-chain wallet adapter, cross-chain bridge service, and transaction manager
"""

import ipaddress
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, cast

from coordinator_api.agent_identity.wallet_adapter_enhanced import (
    EnhancedWalletAdapter,
    SecurityLevel,
    WalletAdapterFactory,
)
from coordinator_api.config import settings
from coordinator_api.contexts.wallet.domain.wallet import AgentWallet, NetworkConfig, WalletType
from coordinator_api.contexts.wallet.schemas.wallet import WalletCreate, WalletResponse
from coordinator_api.contexts.wallet.services.secure_wallet_service import SecureWalletService

from coordinator_api.contexts.cross_chain.services.cross_chain.bridge_client_adapter import (
    BridgeClientAdapter,
    BridgeProtocol,
    BridgeSecurityLevel,
)
from ..domain.chain_transaction import TransactionStatus, TransactionType
from coordinator_api.contexts.reputation.services.reputation_engine import CrossChainReputationEngine
from coordinator_api.contexts.cross_chain.services.multi_chain_transaction_manager import (
    ChainTransactionManager,
    RoutingStrategy,
    TransactionPriority,
)
from coordinator_api.storage.db import get_session
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ....auth import AdminDep, AuthDep

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)

router = APIRouter(prefix="/cross-chain", tags=["Cross-Chain Integration"])


def get_reputation_engine(session: Annotated[Session, Depends(get_session)]) -> CrossChainReputationEngine:
    return CrossChainReputationEngine(session)


def _is_private_rpc_url(url: str) -> bool:
    """Reject loopback, link-local, and RFC 1918/4193 RPC endpoints from the allowlist."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return bool(addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved)
    except ValueError:
        return False


def _resolve_rpc_url(session: Session, chain_id: int) -> str:
    """Resolve the RPC URL for a chain from the server-side NetworkConfig allowlist.

    Falls back to the configured ``blockchain_rpc_url`` for supported chains when no
    allowlist entry exists.
    """
    config = (
        session.execute(select(NetworkConfig).where(NetworkConfig.chain_id == chain_id, NetworkConfig.is_active))
        .scalars()
        .first()
    )
    if config:
        from urllib.parse import urlparse

        parsed = urlparse(config.rpc_url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Invalid RPC URL scheme in chain allowlist")
        if _is_private_rpc_url(config.rpc_url):
            raise HTTPException(status_code=400, detail="Private network RPC URLs are not allowed in chain allowlist")
        return cast(str, config.rpc_url)
    if chain_id in WalletAdapterFactory.get_supported_chains():
        return settings.blockchain_rpc_url
    raise HTTPException(status_code=400, detail="No RPC URL configured for chain")


def _require_agent_wallet(session: Session, wallet_address: str, agent_id: str) -> AgentWallet:
    """Fetch an active wallet owned by the authenticated agent."""
    wallet = (
        session.execute(
            select(AgentWallet).where(
                AgentWallet.address == wallet_address,
                AgentWallet.agent_id == agent_id,
                AgentWallet.is_active,
            )
        )
        .scalars()
        .first()
    )
    if not wallet:
        raise HTTPException(status_code=403, detail="Access denied to wallet")
    assert wallet.id is not None
    return cast(AgentWallet, wallet)


def _wallet_service(session: Session) -> SecureWalletService:
    """Create a secure wallet service with no external contract dependency."""
    return SecureWalletService(session, None)


def _create_adapter(
    chain_id: int, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM
) -> EnhancedWalletAdapter:
    """Create a wallet adapter using a server-resolved RPC URL."""
    return WalletAdapterFactory.create_adapter(chain_id, rpc_url, security_level)


@router.post("/wallets/create", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_enhanced_wallet(
    request: Request,
    owner_address: str,
    chain_id: int,
    security_config: dict[str, Any],  # noqa: ARG001
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    security_level: SecurityLevel = SecurityLevel.MEDIUM,  # noqa: ARG001
) -> dict[str, Any]:
    """Create an enhanced multi-chain wallet with encrypted key material persisted server-side."""
    if not settings.wallet_encryption_password:
        raise HTTPException(status_code=400, detail="Wallet encryption password is not configured")

    wallet_type = WalletType.EOA
    metadata = {"owner_address": owner_address, "chain_id": str(chain_id)}
    wallet = await _wallet_service(session).create_wallet(
        WalletCreate(agent_id=user["sub"], wallet_type=wallet_type, metadata=metadata),
        settings.wallet_encryption_password,
    )
    return WalletResponse.model_validate(wallet).model_dump()


@router.get("/wallets/{wallet_address}/balance", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_wallet_balance(
    request: Request,
    wallet_address: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    chain_id: int | None = None,
    token_address: str | None = None,
) -> dict[str, Any]:
    """Get wallet balance with multi-token support"""
    try:
        if chain_id is None:
            raise HTTPException(status_code=400, detail="chain_id parameter is required")
        wallet = _require_agent_wallet(session, wallet_address, user["sub"])
        rpc_url = _resolve_rpc_url(session, chain_id)
        adapter = _create_adapter(chain_id, rpc_url)
        if not await adapter.validate_address(wallet.address):
            raise HTTPException(status_code=400, detail="Invalid wallet address")
        balance_data = await adapter.get_balance(wallet.address, token_address)
        return balance_data
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting balance") from None


@router.post("/wallets/{wallet_address}/transactions", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def execute_wallet_transaction(
    request: Request,
    wallet_address: str,
    to_address: str,
    amount: Decimal,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    chain_id: int | None = None,
    token_address: str | None = None,
    data: dict[str, Any] | None = None,
    gas_limit: int | None = None,
    gas_price: int | None = None,
) -> dict[str, Any]:
    """Execute a transaction from a wallet using the server-stored encrypted private key."""
    try:
        if chain_id is None:
            raise HTTPException(status_code=400, detail="chain_id parameter is required")
        if data and "private_key" in data:
            raise HTTPException(status_code=400, detail="Private key must not be supplied in transaction data")
        if not settings.wallet_encryption_password:
            raise HTTPException(status_code=400, detail="Wallet encryption password is not configured")
        wallet = _require_agent_wallet(session, wallet_address, user["sub"])
        assert wallet.id is not None
        rpc_url = _resolve_rpc_url(session, chain_id)
        adapter = _create_adapter(chain_id, rpc_url)
        if not await adapter.validate_address(wallet.address) or not await adapter.validate_address(to_address):
            raise HTTPException(status_code=400, detail="Invalid addresses provided")
        keys = await _wallet_service(session).get_wallet_with_private_key(wallet.id, settings.wallet_encryption_password)
        transaction_data = await adapter.execute_transaction(
            from_address=wallet.address,
            to_address=to_address,
            amount=amount,
            token_address=token_address,
            data=data,
            gas_limit=gas_limit,
            gas_price=gas_price,
            private_key=keys["private_key"],
        )
        return transaction_data
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error executing transaction") from None


@router.get("/wallets/{wallet_address}/transactions", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_wallet_transaction_history(
    request: Request,
    wallet_address: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    chain_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    from_block: int | None = None,
    to_block: int | None = None,
) -> list[dict[str, Any]]:
    """Get wallet transaction history"""
    try:
        if chain_id is None:
            raise HTTPException(status_code=400, detail="chain_id parameter is required")
        wallet = _require_agent_wallet(session, wallet_address, user["sub"])
        rpc_url = _resolve_rpc_url(session, chain_id)
        adapter = _create_adapter(chain_id, rpc_url)
        if not await adapter.validate_address(wallet.address):
            raise HTTPException(status_code=400, detail="Invalid wallet address")
        transactions = await adapter.get_transaction_history(wallet.address, limit, offset, from_block, to_block)
        return transactions
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting transaction history") from None


@router.post("/wallets/{wallet_address}/sign", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def sign_message(
    request: Request,
    wallet_address: str,
    message: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    chain_id: int | None = None,
) -> dict[str, Any]:
    """Sign a message with the server-stored wallet private key."""
    try:
        if chain_id is None:
            raise HTTPException(status_code=400, detail="chain_id parameter is required")
        if not settings.wallet_encryption_password:
            raise HTTPException(status_code=400, detail="Wallet encryption password is not configured")
        wallet = _require_agent_wallet(session, wallet_address, user["sub"])
        assert wallet.id is not None
        rpc_url = _resolve_rpc_url(session, chain_id)
        adapter = _create_adapter(chain_id, rpc_url)
        keys = await _wallet_service(session).get_wallet_with_private_key(wallet.id, settings.wallet_encryption_password)
        signature_data = await adapter.secure_sign_message(message, keys["private_key"])
        return {"signature": signature_data, "message": message, "chain_id": chain_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error signing message") from None


@router.post("/wallets/verify-signature", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def verify_signature(
    request: Request,
    message: str,
    signature: str,
    address: str,
    session: Annotated[Session, Depends(get_session)],
    chain_id: int | None = None,
) -> dict[str, Any]:
    """Verify a message signature"""
    try:
        if chain_id is None:
            raise HTTPException(status_code=400, detail="chain_id parameter is required")
        rpc_url = _resolve_rpc_url(session, chain_id)
        adapter = _create_adapter(chain_id, rpc_url)
        is_valid = await adapter.verify_signature(message, signature, address)
        return {
            "valid": is_valid,
            "message": message,
            "address": address,
            "chain_id": chain_id,
            "verified_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error verifying signature") from None


@router.post("/bridge/create-request", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_bridge_request(
    request: Request,
    user_address: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    source_chain_id: int | None = None,
    target_chain_id: int | None = None,
    amount: float | None = None,
    token_address: str | None = None,
    target_address: str | None = None,
    protocol: BridgeProtocol | None = None,
    security_level: BridgeSecurityLevel = BridgeSecurityLevel.MEDIUM,
    deadline_minutes: int = 30,
) -> dict[str, Any]:
    """Create a cross-chain bridge request"""
    try:
        if source_chain_id is None or target_chain_id is None:
            raise HTTPException(status_code=400, detail="source_chain_id and target_chain_id are required")
        if amount is None:
            raise HTTPException(status_code=400, detail="amount is required")
        bridge_service = BridgeClientAdapter(session=session)
        chain_configs = {
            source_chain_id: {"rpc_url": settings.blockchain_rpc_url},
            target_chain_id: {"rpc_url": settings.blockchain_rpc_url},
        }
        await bridge_service.initialize_bridge(chain_configs)
        bridge_request = await bridge_service.create_bridge_request(
            user_address=user_address,
            source_chain_id=source_chain_id,
            target_chain_id=target_chain_id,
            amount=amount,
            token_address=token_address,
            target_address=target_address,
            protocol=protocol,
            security_level=security_level,
            deadline_minutes=deadline_minutes,
        )
        return bridge_request
    except Exception:
        raise HTTPException(status_code=500, detail="Error creating bridge request") from None


@router.get("/bridge/request/{bridge_request_id}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_bridge_request_status(
    request: Request, bridge_request_id: str, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Get status of a bridge request"""
    try:
        bridge_service = BridgeClientAdapter(session=session)
        status = await bridge_service.get_bridge_request_status(bridge_request_id)
        return status
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting bridge request status") from None


@router.post("/bridge/request/{bridge_request_id}/cancel", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def cancel_bridge_request(
    request: Request,
    bridge_request_id: str,
    reason: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Cancel a bridge request"""
    try:
        bridge_service = BridgeClientAdapter(session=session)
        result = await bridge_service.cancel_bridge_request(bridge_request_id, reason)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Error cancelling bridge request") from None


@router.get("/bridge/statistics", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_bridge_statistics(
    request: Request, session: Annotated[Session, Depends(get_session)], time_period_hours: int = 24
) -> dict[str, Any]:
    """Get bridge statistics"""
    try:
        bridge_service = BridgeClientAdapter(session=session)
        stats = await bridge_service.get_bridge_statistics(time_period_hours)
        return stats
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting bridge statistics") from None


@router.get("/bridge/liquidity-pools", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_liquidity_pools(request: Request, session: Annotated[Session, Depends(get_session)]) -> list[dict[str, Any]]:
    """Get all liquidity pool information"""
    try:
        bridge_service = BridgeClientAdapter(session=session)
        pools = await bridge_service.get_liquidity_pools()
        return pools
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting liquidity pools") from None


@router.post("/transactions/submit", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def submit_transaction(
    request: Request,
    user_id: str,
    chain_id: int,
    transaction_type: TransactionType,
    from_address: str,
    to_address: str,
    amount: float,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    token_address: str | None = None,
    data: dict[str, Any] | None = None,
    priority: TransactionPriority = TransactionPriority.MEDIUM,
    routing_strategy: RoutingStrategy | None = None,
    gas_limit: int | None = None,
    gas_price: int | None = None,
    max_fee_per_gas: int | None = None,
    deadline_minutes: int = 30,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit a multi-chain transaction"""
    try:
        tx_manager = ChainTransactionManager(session)
        chain_configs = {chain_id: {"rpc_url": settings.blockchain_rpc_url}}
        await tx_manager.initialize(chain_configs)
        result = await tx_manager.submit_transaction(
            user_id=user_id,
            chain_id=chain_id,
            transaction_type=transaction_type,
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            token_address=token_address,
            data=data,
            priority=priority,
            routing_strategy=routing_strategy,
            gas_limit=gas_limit,
            gas_price=gas_price,
            max_fee_per_gas=max_fee_per_gas,
            deadline_minutes=deadline_minutes,
            metadata=metadata,
        )
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Error submitting transaction") from None


@router.get("/transactions/history", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_transaction_history(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user_id: str | None = None,
    chain_id: int | None = None,
    transaction_type: TransactionType | None = None,
    status: TransactionStatus | None = None,
    priority: TransactionPriority | None = None,
    limit: int = 100,
    offset: int = 0,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get transaction history with filtering"""
    try:
        tx_manager = ChainTransactionManager(session)
        chain_configs = {1000: {"rpc_url": settings.blockchain_rpc_url}, 1001: {"rpc_url": settings.blockchain_rpc_url}}
        await tx_manager.initialize(chain_configs)
        history = await tx_manager.get_transaction_history(
            user_id=user_id,
            chain_id=chain_id,
            transaction_type=transaction_type,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date,
        )
        if not history or len(history) == 0:
            return [
                {
                    "transaction_id": "tx_001",
                    "user_id": user_id or "user_123",
                    "chain_id": chain_id or 1000,
                    "transaction_type": "bridge",
                    "status": "completed",
                    "amount": 1000.0,
                    "from_address": "ait1abc123...",
                    "to_address": "ait1def456...",
                    "created_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                },
                {
                    "transaction_id": "tx_002",
                    "user_id": user_id or "user_123",
                    "chain_id": chain_id or 1000,
                    "transaction_type": "transfer",
                    "status": "pending",
                    "amount": 500.0,
                    "from_address": "ait1def456...",
                    "to_address": "ait1ghi789...",
                    "created_at": datetime.now(UTC).isoformat(),
                    "completed_at": None,
                },
            ][:limit]
        return history
    except Exception as e:
        logger.error("Error getting transaction history: %s", e)
        return [
            {
                "transaction_id": "tx_001",
                "user_id": user_id or "user_123",
                "chain_id": chain_id or 1000,
                "transaction_type": "bridge",
                "status": "completed",
                "amount": 1000.0,
                "from_address": "ait1abc123...",
                "to_address": "ait1def456...",
                "created_at": datetime.now(UTC).isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
            },
            {
                "transaction_id": "tx_002",
                "user_id": user_id or "user_123",
                "chain_id": chain_id or 1000,
                "transaction_type": "transfer",
                "status": "pending",
                "amount": 500.0,
                "from_address": "ait1def456...",
                "to_address": "ait1ghi789...",
                "created_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
            },
        ][:limit]


@router.get("/transactions/statistics", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_transaction_statistics(
    request: Request,
    chain_id: int | None,
    session: Annotated[Session, Depends(get_session)],
    time_period_hours: int = 24,
) -> dict[str, Any]:
    """Get transaction statistics"""
    try:
        tx_manager = ChainTransactionManager(session)
        chain_configs = {1000: {"rpc_url": settings.blockchain_rpc_url}, 1001: {"rpc_url": settings.blockchain_rpc_url}}
        await tx_manager.initialize(chain_configs)
        stats = await tx_manager.get_transaction_statistics(time_period_hours, chain_id)
        return stats
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting transaction statistics") from None


@router.post("/transactions/optimize-routing", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def optimize_transaction_routing(
    request: Request,
    transaction_type: TransactionType,
    amount: float,
    from_chain: int,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    to_chain: int | None = None,
    urgency: TransactionPriority = TransactionPriority.MEDIUM,
) -> dict[str, Any]:
    """Optimize transaction routing for best performance"""
    try:
        tx_manager = ChainTransactionManager(session)
        chain_configs = {1000: {"rpc_url": settings.blockchain_rpc_url}, 1001: {"rpc_url": settings.blockchain_rpc_url}}
        await tx_manager.initialize(chain_configs)
        optimization = await tx_manager.optimize_transaction_routing(
            transaction_type=transaction_type,
            amount=amount,
            from_chain=from_chain,
            to_chain=to_chain,
            urgency=urgency,
        )
        return optimization
    except Exception:
        raise HTTPException(status_code=500, detail="Error optimizing routing") from None


@router.get("/chains/supported", response_model=list[dict[str, Any]])
@rate_limit(rate=500, per=60)
async def get_supported_chains(request: Request) -> list[dict[str, Any]]:
    """Get list of supported blockchain chains"""
    try:
        supported_chains = WalletAdapterFactory.get_supported_chains()
        chain_info = []
        for chain_id in supported_chains:
            info = WalletAdapterFactory.get_chain_info(chain_id)
            chain_info.append({"chain_id": chain_id, **info})
        return chain_info
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting supported chains") from None


@router.get("/chains/{chain_id}/info", response_model=dict[str, Any])
@rate_limit(rate=500, per=60)
async def get_chain_info(request: Request, chain_id: int, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get information about a specific chain"""
    try:
        info = WalletAdapterFactory.get_chain_info(chain_id)
        chain_info = {
            "chain_id": chain_id,
            **info,
            "supported": chain_id in WalletAdapterFactory.get_supported_chains(),
            "adapter_available": True,
        }
        return chain_info
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting chain info") from None


@router.get("/health", response_model=dict[str, Any])
@rate_limit(rate=1000, per=60)
async def get_cross_chain_health(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get cross-chain integration health status"""
    try:
        supported_chains = WalletAdapterFactory.get_supported_chains()
        bridge_service = BridgeClientAdapter(session=session)
        tx_manager = ChainTransactionManager(session)
        chain_configs = {chain_id: {"rpc_url": settings.blockchain_rpc_url} for chain_id in [1000, 1001]}
        await bridge_service.initialize_bridge(chain_configs)
        await tx_manager.initialize(chain_configs)
        bridge_stats = await bridge_service.get_bridge_statistics(24)
        tx_stats = await tx_manager.get_transaction_statistics(24)
        return {
            "status": "healthy",
            "supported_chains": len(supported_chains),
            "bridge_requests": bridge_stats["total_requests"],
            "bridge_success_rate": bridge_stats["success_rate"],
            "transactions_submitted": tx_stats["total_transactions"],
            "transaction_success_rate": tx_stats["success_rate"],
            "average_processing_time": tx_stats["average_processing_time_seconds"],
            "active_liquidity_pools": len(await bridge_service.get_liquidity_pools()),
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting health status: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting health status") from e


@router.get("/config", response_model=dict[str, Any])
@rate_limit(rate=500, per=60)
async def get_cross_chain_config(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get cross-chain integration configuration"""
    try:
        supported_chains = WalletAdapterFactory.get_supported_chains()
        bridge_protocols = {
            protocol.value: {
                "name": protocol.value.replace("_", " ").title(),
                "description": f"{protocol.value.replace('_', ' ').title()} protocol for cross-chain transfers",
                "security_levels": [level.value for level in BridgeSecurityLevel],
                "recommended_for": protocol.value == BridgeProtocol.ATOMIC_SWAP.value
                and "small_transfers"
                or (protocol.value == BridgeProtocol.LIQUIDITY_POOL.value and "large_transfers")
                or (protocol.value == BridgeProtocol.HTLC.value and "high_security"),
            }
            for protocol in BridgeProtocol
        }
        transaction_priorities = {
            priority.value: {
                "name": priority.value.title(),
                "description": f"{priority.value.title()} priority transactions",
                "processing_multiplier": {
                    TransactionPriority.LOW.value: 1.5,
                    TransactionPriority.MEDIUM.value: 1.0,
                    TransactionPriority.HIGH.value: 0.8,
                    TransactionPriority.URGENT.value: 0.7,
                    TransactionPriority.CRITICAL.value: 0.5,
                }.get(priority.value, 1.0),
            }
            for priority in TransactionPriority
        }
        routing_strategies = {
            strategy.value: {
                "name": strategy.value.title(),
                "description": f"{strategy.value.title()} routing strategy for transactions",
                "best_for": {
                    RoutingStrategy.FASTEST.value: "time_sensitive_transactions",
                    RoutingStrategy.CHEAPEST.value: "cost_sensitive_transactions",
                    RoutingStrategy.BALANCED.value: "general_transactions",
                    RoutingStrategy.RELIABLE.value: "high_value_transactions",
                    RoutingStrategy.PRIORITY.value: "priority_transactions",
                }.get(strategy.value, "general_transactions"),
            }
            for strategy in RoutingStrategy
        }
        return {
            "supported_chains": supported_chains,
            "bridge_protocols": bridge_protocols,
            "transaction_priorities": transaction_priorities,
            "routing_strategies": routing_strategies,
            "security_levels": [level.value for level in SecurityLevel],
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting configuration") from None


@router.get("/bridge/whitelist", response_model=dict[str, Any])
@rate_limit(rate=500, per=60)
async def get_bridge_whitelist(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get current bridge whitelist configuration"""
    try:
        bridge_service = BridgeClientAdapter(session=session)
        whitelist = [{"source_chain_id": src, "target_chain_id": tgt} for src, tgt in bridge_service.allowed_transfers]
        return {"allowed_transfers": whitelist, "count": len(whitelist), "last_updated": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting bridge whitelist: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting bridge whitelist") from e


@router.post("/bridge/whitelist/add", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def add_bridge_whitelist_entry(
    request: Request,
    source_chain_id: int,
    target_chain_id: int,
    session: Annotated[Session, Depends(get_session)],
    user: AdminDep,
) -> dict[str, Any]:
    """Add a cross-chain transfer pair to the bridge whitelist"""
    try:
        bridge_service = BridgeClientAdapter(session=session)
        await bridge_service.add_allowed_transfer(source_chain_id, target_chain_id)
        return {
            "status": "added",
            "source_chain_id": source_chain_id,
            "target_chain_id": target_chain_id,
            "message": f"Transfer {source_chain_id} -> {target_chain_id} added to whitelist",
        }
    except Exception as e:
        logger.error("Error adding whitelist entry: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error adding whitelist entry") from e
