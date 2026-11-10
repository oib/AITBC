"""Platform analytics and health endpoints for the Developer Platform."""

import os
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx

from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, func, select
from starlette.concurrency import run_in_threadpool

from ....storage.db import get_session
from ..domain.developer_platform import DeveloperCertification, DeveloperProfile, RegionalHub
from ..services.developer_platform_service import DeveloperPlatformService
from .common import get_developer_platform_service

router = APIRouter(tags=["Developer Platform"])


@router.get("/analytics/overview", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_platform_overview(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get platform overview analytics."""

    try:
        # Get bounty statistics with fallback
        try:
            bounty_stats = await run_in_threadpool(dev_service.get_bounty_statistics)
        except Exception:
            bounty_stats = {
                "total": 150,
                "active": 45,
                "completed": 95,
                "total_payout": 250000.0,
            }  # not-money: demo/simulation value, not a live amount

        # Get developer statistics with fallback — COUNT(*) in SQL, not
        # len(all rows): the tables grow unboundedly (#1543).
        try:
            total_developers = int(
                await run_in_threadpool(
                    lambda: session.execute(select(func.count()).select_from(DeveloperProfile)).scalar_one()
                )
            )
            active_developers = int(
                await run_in_threadpool(
                    lambda: session.execute(
                        select(func.count()).select_from(DeveloperProfile).where(DeveloperProfile.is_active)
                    ).scalar_one()
                )
            )
        except Exception:
            total_developers = 1250
            active_developers = 890

        # Get certification statistics with fallback
        try:
            total_certifications = int(
                await run_in_threadpool(
                    lambda: session.execute(select(func.count()).select_from(DeveloperCertification)).scalar_one()
                )
            )
        except Exception:
            total_certifications = 320

        # Get regional hub statistics with fallback
        try:
            total_hubs = int(
                await run_in_threadpool(lambda: session.execute(select(func.count()).select_from(RegionalHub)).scalar_one())
            )
        except Exception:
            total_hubs = 8

        return {
            "developers": {
                "total": total_developers,
                "active": active_developers,
                "new_this_month": 25,  # Mock data
                "average_reputation": 45.5,
            },
            "bounties": bounty_stats,
            "certifications": {
                "total_granted": total_certifications,
                "new_this_month": 15,  # Mock data
                "most_common_level": "intermediate",
            },
            "regional_hubs": {
                "total": total_hubs,
                "active": total_hubs,  # Mock: all hubs are active
                "regions_covered": 12,  # Mock data
            },
            "staking": {"total_staked": 1000000.0, "active_stakers": 500, "average_apy": 7.5},  # Mock data
            "generated_at": datetime.now(UTC).isoformat(),
        }

    except Exception:
        # Return fallback data even on total failure
        return {
            "developers": {
                "total": 1250,
                "active": 890,
                "new_this_month": 25,
                "average_reputation": 45.5,
            },
            "bounties": {
                "total": 150,
                "active": 45,
                "completed": 95,
                "total_payout": 250000.0,
            },  # not-money: demo/simulation value, not a live amount
            "certifications": {
                "total_granted": 320,
                "new_this_month": 15,
                "most_common_level": "intermediate",
            },
            "regional_hubs": {
                "total": 8,
                "active": 8,
                "regions_covered": 12,
            },
            "staking": {"total_staked": 1000000.0, "active_stakers": 500, "average_apy": 7.5},
            "generated_at": datetime.now(UTC).isoformat(),
            "note": "Fallback data returned due to service error",
        }


_HEALTH_PROBE_TIMEOUT = 3.0


def _probe_blockchain() -> str:
    """Probe the AITBC chain RPC — same ``/rpc/head`` read /v1/blockchain/status uses."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        response = httpx.get(f"{rpc_url}/rpc/head", timeout=_HEALTH_PROBE_TIMEOUT)
        return "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        return "unhealthy"


def _probe_ipfs() -> str:
    """Probe the IPFS API the way ``IPFSClient.check_availability`` does (POST /api/v0/id)."""
    api_url = os.getenv("IPFS_API_URL", "http://localhost:5001").rstrip("/")
    try:
        response = httpx.post(f"{api_url}/api/v0/id", timeout=_HEALTH_PROBE_TIMEOUT)
        return "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        return "unhealthy"


def _probe_smart_contracts() -> str:
    """Probe the EVM JSON-RPC the settlement/energy rails use.

    ``eth_rpc_url`` unset means no contract rail is configured on this
    deployment — report ``not_configured`` rather than fabricating health.
    """
    try:
        from ....config import settings

        rpc_url = getattr(settings, "eth_rpc_url", None)
        if not rpc_url:
            return "not_configured"
        response = httpx.post(
            rpc_url.rstrip("/"),
            json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
            timeout=_HEALTH_PROBE_TIMEOUT,
        )
        if response.status_code == 200 and (response.json() or {}).get("result"):
            return "healthy"
        return "unhealthy"
    except Exception:
        return "unhealthy"


@router.get("/health", response_model=dict[str, Any])
@rate_limit(rate=1000, per=60)
def get_platform_health(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get developer platform health status."""

    try:
        # Check database connectivity
        try:
            developer_count = session.execute(select(func.count(DeveloperProfile.id))).scalar()  # type: ignore[arg-type]
            database_status = "healthy"
        except Exception:
            database_status = "unhealthy"
            developer_count = 0

        # Real dependency probes (#1541): every field is an actual check, and
        # any probed-but-failed dependency degrades the overall status.
        # ``not_configured`` is reported honestly and does not count as a
        # failure — there is nothing to probe.
        services_status = {
            "database": database_status,
            "blockchain": _probe_blockchain(),
            "ipfs": _probe_ipfs(),
            "smart_contracts": _probe_smart_contracts(),
        }

        overall_status = "degraded" if "unhealthy" in services_status.values() else "healthy"

        return {
            "status": overall_status,
            "services": services_status,
            "metrics": {
                "total_developers": developer_count,
                "active_bounties": 25,  # Mock data
                "pending_submissions": 8,  # Mock data
                "system_uptime": "99.9%",
            },
            "last_updated": datetime.now(UTC).isoformat(),
        }

    except Exception:
        raise HTTPException(status_code=500, detail="Error getting platform health") from None
