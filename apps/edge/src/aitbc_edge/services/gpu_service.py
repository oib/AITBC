"""GPU service for Edge API Service"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from aitbc.aitbc_logging import get_logger
from sqlmodel import col, select

from ..clients.gpu_service import GPUServiceClient
from ..config import settings
from ..schemas.gpu import GPUListing
from ..storage import get_session

logger = get_logger(__name__)


def _profile_gpu_id(profile: dict[str, Any]) -> str:
    """Stable mirror key for a remote GPU profile."""
    return str(profile.get("id") or profile.get("hardware_uuid") or "")


def _profile_price(profile: dict[str, Any]) -> Decimal:
    """Best-effort Decimal price; unparseable/missing values mirror as 0."""
    raw = profile.get("price_per_hour")
    if raw in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return Decimal("0")


class GPUService:
    """Service for GPU operations"""

    async def list_gpus(
        self, architecture: str | None = None, edge_optimized: bool | None = None, min_memory_gb: int | None = None
    ) -> list[dict[str, Any]]:
        """List GPUs via GPU service"""
        async with GPUServiceClient() as gpu_client:
            profiles = await gpu_client.get_gpu_profiles(architecture, edge_optimized, min_memory_gb)

        # Mirror the remote profile list into gpu_listings, upserting by
        # gpu_id. The remote list is the source of truth: every call used to
        # append a fresh set of rows, growing the table without bound (#1385).
        async with get_session() as session:
            gpu_ids = [gid for gid in (_profile_gpu_id(p) for p in profiles) if gid]
            existing: dict[str, GPUListing] = {}
            if gpu_ids:
                result = await session.execute(select(GPUListing).where(col(GPUListing.gpu_id).in_(gpu_ids)))
                existing = {g.gpu_id: g for g in result.scalars().all()}

            for profile in profiles:
                gpu_id = _profile_gpu_id(profile)
                if not gpu_id:
                    # No stable key — cannot be upserted or looked up later.
                    continue
                fields = {
                    "model": profile.get("model", "Unknown"),
                    "price_per_hour": _profile_price(profile),
                    "memory_gb": profile.get("memory_gb"),
                    "cuda_version": profile.get("cuda_version", ""),
                    "region": profile.get("region", ""),
                    "capabilities": profile.get("capabilities", []),
                    "extra_data": profile,
                }
                listing = existing.get(gpu_id)
                if listing is None:
                    session.add(GPUListing(gpu_id=gpu_id, **fields))
                else:
                    for key, value in fields.items():
                        setattr(listing, key, value)
                    listing.updated_at = datetime.now(UTC)
            await session.commit()

        return profiles

    async def get_gpu_listing(self, gpu_id: str) -> dict[str, Any] | None:
        """Get GPU listing details"""
        # Get from GPU service
        try:
            async with GPUServiceClient() as gpu_client:
                profiles = await gpu_client.get_gpu_profiles()
            for profile in profiles:
                if profile.get("id") == gpu_id:
                    return profile
            return None
        except Exception:
            # Fall back to database
            from sqlmodel import select

            async with get_session() as session:
                result = await session.execute(select(GPUListing).where(GPUListing.gpu_id == gpu_id))
                gpu = result.scalar_one_or_none()
                if gpu:
                    return {
                        "id": gpu.gpu_id,
                        "model": gpu.model,
                        "memory_gb": gpu.memory_gb,
                        "cuda_version": gpu.cuda_version,
                        "region": gpu.region,
                        "capabilities": gpu.capabilities,
                        "extra_data": gpu.extra_data,
                    }
            return None

    async def remove_gpu_listing(self, gpu_id: str) -> bool:
        """Remove GPU listing from database"""
        from sqlmodel import delete

        async with get_session() as session:
            stmt = delete(GPUListing).where(GPUListing.gpu_id == gpu_id)  # type: ignore[arg-type]
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def scan_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan GPUs via GPU service"""
        async with GPUServiceClient() as gpu_client:
            result = await gpu_client.scan_gpus(miner_id)
        return result

    async def get_gpu_metrics(self, gpu_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get GPU metrics via GPU service"""
        async with GPUServiceClient() as gpu_client:
            metrics = await gpu_client.get_gpu_metrics(gpu_id, limit)
        return metrics

    async def advertise_to_market(self) -> dict[str, Any]:
        """Advertise this edge node's GPU capabilities to the market (v0.6.6).

        POSTs the list of available GPU profiles to the market service so
        that the market can include edge-hosted GPUs in offer discovery.
        """
        import httpx

        async with GPUServiceClient() as gpu_client:
            profiles = await gpu_client.get_gpu_profiles()
        payload = {
            "node_type": "edge",
            "service": "aitbc-edge",
            "gpu_count": len(profiles),
            "gpus": [
                {
                    "model": p.get("model", "Unknown"),
                    "memory_gb": p.get("memory_gb", 0),
                    "region": p.get("region", ""),
                    "capabilities": p.get("capabilities", []),
                }
                for p in profiles
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{settings.market_url}/v1/market/edge-advertise", json=payload)
                resp.raise_for_status()
                return {"status": "advertised", "gpu_count": len(profiles), "response": resp.json()}
        except Exception as e:
            logger.warning("Failed to advertise to market: %s", e)
            return {"status": "failed", "error": str(e), "gpu_count": len(profiles)}
