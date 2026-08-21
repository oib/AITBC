"""Bond router."""

from typing import Any
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(tags=["bond"])

get_bond: Callable[..., Any] | None = None
list_bonds: Callable[..., Any] | None = None

try:
    from ..bond import get_bond, list_bonds
except ImportError as e:
    _logger.error("Bond module not available: %s — bond endpoints will return 503", e)


@router.get("/{bond_id}", summary="Get bond by ID")
@rate_limit(rate=100, per=60)
async def get_bond_route(request: Request, bond_id: str, chain_id: str | None = None) -> dict[str, Any]:
    if get_bond is None:
        raise HTTPException(status_code=503, detail="Bond module not available")
    return await get_bond(request, bond_id, chain_id)  # type: ignore[no-any-return]


@router.get("/provider/{provider}", summary="List bonds for a provider")
@rate_limit(rate=100, per=60)
async def list_bonds_route(request: Request, provider: str, chain_id: str | None = None) -> dict[str, Any]:
    if list_bonds is None:
        raise HTTPException(status_code=503, detail="Bond module not available")
    return await list_bonds(request, provider, chain_id)  # type: ignore[no-any-return]
