"""Bounty lock / memo RPC (V23-42)."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from aitbc.rate_limiting import rate_limit

from ..logger import get_logger
from .retired import raise_for_retired

_logger = get_logger(__name__)


@rate_limit(rate=20, per=60)
async def deploy_bounty(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Bounty (create)")


@rate_limit(rate=20, per=60)
async def submit_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Bounty (submit)")


@rate_limit(rate=20, per=60)
async def verify_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Bounty (verify/payout)")


@rate_limit(rate=20, per=60)
async def dispute_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Bounty (dispute)")


@rate_limit(rate=20, per=60)
async def expire_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    raise_for_retired("Bounty (expire/refund)")
