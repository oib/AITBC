"""FastAPI dependencies and API-key auth for the market service.

Extracted from ``main.py`` — the route handlers depend on these, so they
live in a leaf module both ``main`` and the routers can import without a
cycle. The authenticator *objects* are re-exported through ``main`` because
the test-suite toggles ``auth_enabled``/``expected_key`` on them via
``market_service.main._market_user_key_auth``.
"""

import hmac
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from aitbc.auth import APIKeyAuthenticator

from .config import settings
from .services.market_service import MarketService
from .services.matching_service import MatchingService
from .storage import get_session


async def get_market_service(session: Annotated[AsyncSession, Depends(get_session)]) -> MarketService:
    """Get market service instance"""
    return MarketService(session)


async def get_matching_service(session: Annotated[AsyncSession, Depends(get_session)]) -> MatchingService:
    """Get matching service instance"""
    return MatchingService(session)


get_session_dep = get_session


_market_user_key_auth = APIKeyAuthenticator(
    expected_key=settings.api_key,
    auth_enabled=settings.auth_enabled,
    success_role="market_admin",
)
_market_operator_key_auth = APIKeyAuthenticator(
    expected_key=settings.operator_api_key,
    auth_enabled=settings.auth_enabled,
    success_role="market_operator",
)


async def require_market_api_key(request: HTTPConnection) -> dict[str, Any]:
    """Accept the user-tier key or the operator-tier key (#1893).

    ``MARKET_API_KEY`` is distributed to users (CLI ``market`` commands), so
    holding it must not confer operator powers. ``MARKET_OPERATOR_API_KEY``
    is the service/tooling credential; ``_is_operator`` tells the tiers
    apart by which key was presented.
    """
    try:
        return await _market_user_key_auth(request)
    except HTTPException:
        return await _market_operator_key_auth(request)


require_market_operator_key = _market_operator_key_auth


def _is_operator(request: Request) -> bool:
    """True when the caller presented the operator-tier key (or auth is off).

    Same header as ``require_market_api_key``; the presented value decides
    the tier. An operator key equal to the user key would make every holder
    an operator, so equality fails closed.
    """
    # Effective flag, not the setting: tests toggle the authenticators'
    # auth_enabled per-test, and auth-disabled means the operator tier is
    # open (same semantics as the dependency itself).
    if not (_market_user_key_auth.auth_enabled and _market_operator_key_auth.auth_enabled):
        return True
    expected = _market_operator_key_auth.expected_key
    if not expected or expected == _market_user_key_auth.expected_key:
        return False
    presented = request.headers.get("X-Api-Key")
    return bool(presented) and hmac.compare_digest(str(presented), str(expected))


def _is_market_admin(request: Request) -> bool:
    """True when the caller carries either service key (or auth is disabled).

    Same semantics as ``require_market_api_key`` but non-raising, for routes
    that stay public and only upgrade the response for an admin caller.
    """
    if not settings.auth_enabled:
        return True
    presented = request.headers.get("X-Api-Key")
    if not presented:
        return False
    return any(
        expected and hmac.compare_digest(str(presented), str(expected))
        for expected in (settings.api_key, settings.operator_api_key)
    )
