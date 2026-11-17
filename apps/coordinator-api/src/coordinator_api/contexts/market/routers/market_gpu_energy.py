"""Native energy profile/rate endpoints split from ``market_gpu`` (pure-move).

Self-contained: no facade helpers, safe to import directly.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from aitbc.aitbc_logging import get_logger
from aitbc.market.energy_pricing import NATIVE_UNITS_PER_AIT
from aitbc.market.energy_oracle import EnergyOracleError
from aitbc.rate_limiting import rate_limit

from ....auth import MinerDep
from ....config import settings
from ....storage.db import get_session
from ..domain.energy import NativeEnergyProfile, NativeEnergyRate
from ..services.native_energy import NativeEnergyOracle

logger = get_logger(__name__)

router = APIRouter()


@router.post("/market/native-energy/profile", status_code=http_status.HTTP_201_CREATED)
@rate_limit(rate=30, per=60)
def register_native_energy_profile(
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Register or update an AIT-native energy profile for a GPU resource."""
    data = request.get("profile") or request
    resource_id = data.get("resource_id")
    if not resource_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="resource_id is required")

    scale = 10**18
    eur = data.get("eur_per_kwh")
    try:
        eur_scaled = int(Decimal(str(eur)) * scale) if eur is not None else int(data.get("eur_per_kwh_scaled", 0))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="eur_per_kwh is not a valid number") from None

    tbp = int(data.get("tbp_watts", 0))
    if tbp <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="tbp_watts must be positive")
    if eur_scaled <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="eur_per_kwh must be positive")

    existing = session.get(NativeEnergyProfile, resource_id)
    if existing:
        existing.provider = data.get("provider", existing.provider)
        existing.model_id = data.get("model_id", existing.model_id)
        existing.tbp_watts = tbp
        existing.eur_per_kwh_scaled = eur_scaled
        existing.enabled = data.get("enabled", True)
        existing.revision += 1
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        profile = NativeEnergyProfile(
            resource_id=resource_id,
            provider=data.get("provider", user.get("sub", "")),
            model_id=data.get("model_id", resource_id),
            tbp_watts=tbp,
            eur_per_kwh_scaled=eur_scaled,
            enabled=data.get("enabled", True),
            revision=1,
        )
        session.add(profile)
    session.commit()

    return {
        "resource_id": resource_id,
        "status": "registered",
        "tbp_watts": tbp,
        "eur_per_kwh_scaled": eur_scaled,
    }


@router.post("/market/native-energy/rate")
@rate_limit(rate=30, per=60)
def publish_native_energy_rate(
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Publish or update the global AIT/EUR rate for native energy quotes."""
    data = request.get("rate") or request
    scale = 10**18
    ait_per_eur = data.get("ait_per_eur")
    try:
        ait_scaled = (
            int(Decimal(str(ait_per_eur)) * scale) if ait_per_eur is not None else int(data.get("ait_per_eur_scaled", 0))
        )
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="ait_per_eur is not a valid number") from None
    if ait_scaled <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="ait_per_eur must be positive")
    if ait_scaled > 9_223_372_036_854_775_807:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="ait_per_eur exceeds the int64 scaled range")
    rate_ait = Decimal(ait_scaled) / Decimal(scale)
    if rate_ait < settings.energy_rate_min_ait_per_eur or rate_ait > settings.energy_rate_max_ait_per_eur:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"ait_per_eur {rate_ait} outside the plausible band "
                f"[{settings.energy_rate_min_ait_per_eur}, {settings.energy_rate_max_ait_per_eur}]"
            ),
        )

    now = int(datetime.now(UTC).timestamp())
    existing = session.get(NativeEnergyRate, 1)
    if existing:
        existing.ait_per_eur_scaled = ait_scaled
        existing.version = existing.version + 1
        existing.observed_at = data.get("observed_at", now)
        existing.submitted_at = now
        existing.source_kind = data.get("source_kind", "native_operator")
        existing.enabled = data.get("enabled", True)
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        rate = NativeEnergyRate(
            id=1,
            ait_per_eur_scaled=ait_scaled,
            version=1,
            observed_at=data.get("observed_at", now),
            submitted_at=now,
            source_kind=data.get("source_kind", "native_operator"),
            enabled=data.get("enabled", True),
        )
        session.add(rate)
    session.commit()

    return {
        "ait_per_eur_scaled": ait_scaled,
        "version": existing.version if existing else 1,
        "status": "published",
    }


@router.get("/market/native-energy/profile/{resource_id}")
def get_native_energy_profile(resource_id: str, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Read the registered AIT-native energy profile for a resource."""
    try:
        profile = session.get(NativeEnergyProfile, resource_id)
    except OperationalError:
        # Follower coordinators can lack the native pricing tables entirely.
        profile = None
    if profile is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"no energy profile for {resource_id}")
    return {
        "resource_id": profile.resource_id,
        "provider": profile.provider,
        "model_id": profile.model_id,
        "tbp_watts": profile.tbp_watts,
        "eur_per_kwh_scaled": profile.eur_per_kwh_scaled,
        "eur_per_kwh": str(Decimal(profile.eur_per_kwh_scaled) / Decimal(10**18)),
        "enabled": profile.enabled,
        "revision": profile.revision,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.get("/market/native-energy/rate")
def get_native_energy_rate(session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Read the published global AIT/EUR rate for native energy quotes."""
    try:
        rate = session.get(NativeEnergyRate, 1)
    except OperationalError:
        rate = None
    if rate is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="no native energy rate configured")
    return {
        "ait_per_eur_scaled": rate.ait_per_eur_scaled,
        "ait_per_eur": str(Decimal(rate.ait_per_eur_scaled) / Decimal(10**18)),
        "version": rate.version,
        "source_kind": rate.source_kind,
        "enabled": rate.enabled,
        "updated_at": rate.updated_at.isoformat() if rate.updated_at else None,
    }


@router.get("/market/native-energy/floor")
def get_native_energy_floor(
    resource_id: str,
    session: Annotated[Session, Depends(get_session)],
    gpu_count: int = Query(default=1, ge=1),
    duration_seconds: int = Query(default=3600, ge=1),
) -> dict[str, Any]:
    """Compute the native energy floor for the given rental terms.

    Same arithmetic as the quote builder, exposed as a read so shops and
    CLI tooling can check the floor without signing a quote.
    """
    oracle = NativeEnergyOracle(session)
    try:
        net_units = oracle.get_energy_floor(
            resource_id=resource_id,
            gpu_count=gpu_count,
            duration_seconds=duration_seconds,
            settlement_unit_scale=NATIVE_UNITS_PER_AIT,
        )
    except EnergyOracleError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OperationalError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="native energy tables not provisioned on this coordinator",
        ) from None
    return {
        "resource_id": resource_id,
        "gpu_count": gpu_count,
        "duration_seconds": duration_seconds,
        "settlement_unit_scale": NATIVE_UNITS_PER_AIT,
        "net_floor_units": net_units,
        "net_floor_ait": str(Decimal(net_units) / Decimal(NATIVE_UNITS_PER_AIT)),
        "rail": "native",
    }
