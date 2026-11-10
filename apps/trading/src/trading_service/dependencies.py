"""Shared FastAPI dependencies for the Trading Service."""

import hashlib
import hmac
import os
import time
from collections.abc import AsyncIterator
from typing import Annotated

from aitbc.auth import APIKeyAuthenticator
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


require_trading_api_key = APIKeyAuthenticator(
    expected_key=os.environ.get("TRADING_API_KEY"),
    auth_enabled=True,
    header_name="X-Trading-Api-Key",
    success_role="trading",
)


# Webhook signatures must cover a timestamp so a captured
# ``payment_id:tx_hash`` pair cannot be replayed forever (#1423, #1577).
# The signer sends ``X-Timestamp`` (unix seconds); signatures older or
# newer than ``EXCHANGE_WEBHOOK_MAX_SKEW_SECONDS`` (default 300) are
# refused. The skew window bounds replay to a few minutes; true
# once-only semantics additionally need the payment-state check in the
# (currently disabled) confirm endpoint.
_WEBHOOK_MAX_SKEW_ENV = "EXCHANGE_WEBHOOK_MAX_SKEW_SECONDS"
_WEBHOOK_DEFAULT_SKEW = 300


def _webhook_max_skew() -> int:
    try:
        return int(os.environ.get(_WEBHOOK_MAX_SKEW_ENV, "") or _WEBHOOK_DEFAULT_SKEW)
    except ValueError:
        return _WEBHOOK_DEFAULT_SKEW


async def require_webhook_signature(
    x_signature: str = Header(default="", alias="X-Signature"),
    x_timestamp: str = Header(default="", alias="X-Timestamp"),
    payment_id: str = Path(...),
    tx_hash: str = Query(...),
) -> None:
    """Validate the HMAC-SHA256 signature on a payment webhook.

    Signed payload: ``{payment_id}:{tx_hash}:{X-Timestamp}``. The timestamp
    must be a unix-seconds integer within the configured skew window of
    now — an old signature is rejected even though its HMAC still matches.
    """
    secret = os.environ.get("EXCHANGE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    try:
        timestamp = int(x_timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature") from None
    if abs(time.time() - timestamp) > _webhook_max_skew():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Stale webhook signature")
    expected = hmac.new(secret.encode(), f"{payment_id}:{tx_hash}:{timestamp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
