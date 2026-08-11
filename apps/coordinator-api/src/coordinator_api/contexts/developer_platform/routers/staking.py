"""Staking and rewards endpoints for the Developer Platform."""

from decimal import Decimal
from typing import Annotated, Any

from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ....storage.db import get_session
from ..services.developer_platform_service import DeveloperPlatformService
from .common import get_developer_platform_service

router = APIRouter(tags=["Developer Platform"])


@router.post("/stake", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def stake_on_developer(
    request: Request,
    staker_address: str,
    developer_address: str,
    amount: Decimal,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Stake tokens on a developer.

    ponytail: Disabled until real on-chain staking is implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Developer staking is disabled until on-chain staking is implemented",
    )


@router.get("/staking/{address}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_staking_info(
    request: Request,
    address: str,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get staking information for an address.

    ponytail: Disabled until staking is backed by real on-chain data.
    """
    raise HTTPException(
        status_code=501,
        detail="Staking information is disabled until on-chain staking is implemented",
    )


@router.post("/unstake", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def unstake_tokens(
    request: Request,
    staking_id: str,
    amount: Decimal,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Unstake tokens from a developer.

    ponytail: Disabled until real on-chain unstaking is implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Developer unstaking is disabled until on-chain staking is implemented",
    )


@router.get("/rewards/{address}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_rewards(
    request: Request,
    address: str,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get reward information for an address.

    ponytail: Disabled until rewards are backed by real on-chain data.
    """
    raise HTTPException(
        status_code=501,
        detail="Reward information is disabled until on-chain reward distribution is implemented",
    )


@router.post("/claim-rewards", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def claim_rewards(
    request: Request,
    address: str,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Claim pending rewards.

    ponytail: Disabled until on-chain reward claiming is implemented.
    The current implementation mints tokens without verification.
    """
    raise HTTPException(
        status_code=501,
        detail="Reward claiming is disabled until on-chain reward distribution is implemented",
    )


@router.get("/staking-stats", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_staking_statistics(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get comprehensive staking statistics.

    ponytail: Disabled until staking is backed by real on-chain data.
    """
    raise HTTPException(
        status_code=501,
        detail="Staking statistics are disabled until on-chain staking is implemented",
    )
