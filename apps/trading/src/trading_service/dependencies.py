"""Shared FastAPI dependencies for the Trading Service."""

import hashlib
import hmac
import os
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from .clients.blockchain import BlockchainClient
from .config import settings
from .services.chain_discovery import ChainDiscoveryService
from .services.inter_chain_service import InterChainTradeService
from .services.matching_engine import MatchingEngine
from .services.offer_sync_service import OfferSyncService
from .services.trading_service import TradingService
from .storage import get_session


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """Get database session dependency."""
    async with get_session() as session:
        yield session


async def get_trading_service(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> TradingService:
    """Get trading service instance."""
    return TradingService(session)


async def get_chain_discovery(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> ChainDiscoveryService:
    """Get chain discovery service instance."""
    return ChainDiscoveryService(session, BlockchainClient(rpc_url=settings.blockchain_rpc_url))


async def get_inter_chain_service(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> InterChainTradeService:
    """Get inter-chain trade service instance."""
    return InterChainTradeService(session)


async def get_matching_engine(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> MatchingEngine:
    """Get matching engine instance."""
    return MatchingEngine(session)


async def get_offer_sync_service(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> OfferSyncService:
    """Get offer sync service instance."""
    return OfferSyncService(session)


async def require_trading_api_key(
    x_trading_api_key: str | None = Header(default=None, alias="X-Trading-Api-Key"),
) -> None:
    """Validate the trading API key header."""
    expected = os.environ.get("TRADING_API_KEY")
    if not x_trading_api_key or not expected or not hmac.compare_digest(x_trading_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


async def require_webhook_signature(
    x_signature: str = Header(..., alias="X-Signature"),
    payment_id: str = Path(...),
    tx_hash: str = Query(...),
) -> None:
    """Validate the HMAC-SHA256 signature on a payment webhook."""
    secret = os.environ.get("EXCHANGE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    expected = hmac.new(
        secret.encode(), f"{payment_id}:{tx_hash}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
