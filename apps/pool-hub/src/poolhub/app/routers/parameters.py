"""Governance-triggered parameter change router for pool hub (v0.7.4 §B3).

Provides an endpoint for the governance service to apply parameter changes
that have been approved via on-chain governance proposals. Validates that
the proposal ID is provided and the parameter change is well-formed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from aitbc.auth import APIKeyAuthenticator
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db_session as get_db
from ...settings import settings
from ...models import ServiceConfig

router = APIRouter(prefix="/parameters", tags=["parameters"])


class ParameterChangeRequest(BaseModel):
    """Request body for applying a governance-approved parameter change."""

    proposal_id: str = Field(..., description="Governance proposal ID that approved this change")
    target_service: str = Field(..., description="Service type to update (e.g. whisper, llm_inference)")
    parameter_name: str = Field(..., description="Name of the parameter to change")
    old_value: Any = Field(default=None, description="Expected old value (for validation)")
    new_value: Any = Field(..., description="New value to apply")
    description: str = Field(default="", description="Human-readable description of the change")


class ParameterChangeResponse(BaseModel):
    """Response after applying a parameter change."""

    proposal_id: str
    applied: bool
    parameter_name: str
    old_value: Any
    new_value: Any
    applied_at: str
    message: str = ""


# Allowed parameters that governance can change
GOVERNANCE_PARAMETERS: dict[str, type] = {
    "max_concurrent": int,
    "enabled": bool,
    "pricing": dict,
    "config": dict,
    "capabilities": list,
}


_governance_auth = APIKeyAuthenticator(
    expected_key=settings.coordinator_shared_secret,
    auth_enabled=True,
    header_name="X-PoolHub-Key",
    success_role="governance",
)


@router.post("/apply", response_model=ParameterChangeResponse)
async def apply_parameter_change(
    change: ParameterChangeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(_governance_auth)],
) -> ParameterChangeResponse:
    """Apply a governance-approved parameter change to pool-hub service config.

    The proposal_id must be provided — this endpoint is called by the
    governance service after a proposal has passed and the timelock has
    expired. The parameter change is validated against the allowed
    parameters list.
    """
    # Validate parameter is governance-controllable
    if change.parameter_name not in GOVERNANCE_PARAMETERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter '{change.parameter_name}' is not governance-controllable. "
            f"Allowed: {list(GOVERNANCE_PARAMETERS.keys())}",
        )

    # Validate type of new_value
    expected_type = GOVERNANCE_PARAMETERS[change.parameter_name]
    if not isinstance(change.new_value, expected_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter '{change.parameter_name}' expects type {expected_type.__name__}, "
            f"got {type(change.new_value).__name__}",
        )

    # Governance changes are service-wide: ServiceConfig is keyed per-miner
    # (miner_id + service_type) and the request carries no miner_id, so the
    # change applies to every config row for the target service type.
    stmt = select(ServiceConfig).where(ServiceConfig.service_type == change.target_service)
    result = await db.execute(stmt)
    configs = list(result.scalars().all())

    if not configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service config for '{change.target_service}' not found",
        )

    # Parameter names map 1:1 onto ServiceConfig columns. Snapshot each row's
    # current value first (copying mutable JSON values) so an old_value
    # mismatch 409s before any row is mutated.
    old_values: list[Any] = []
    for config in configs:
        old = getattr(config, change.parameter_name)
        if isinstance(old, dict):
            old = dict(old)
        elif isinstance(old, list):
            old = list(old)
        old_values.append(old)

    for old_value in old_values:
        # old_value must match every miner's row, otherwise the
        # governance-approved baseline does not hold fleet-wide.
        if change.old_value is not None and old_value != change.old_value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Expected old value {change.old_value!r} does not match actual {old_value!r}",
            )

    now = datetime.now(UTC)
    for config in configs:
        setattr(config, change.parameter_name, change.new_value)
        config.updated_at = now

    await db.commit()

    return ParameterChangeResponse(
        proposal_id=change.proposal_id,
        applied=True,
        parameter_name=change.parameter_name,
        old_value=old_values[0] if len(old_values) == 1 else old_values,
        new_value=change.new_value,
        applied_at=datetime.now(UTC).isoformat(),
        message=(
            f"Parameter '{change.parameter_name}' updated for service "
            f"'{change.target_service}' on {len(configs)} miner config(s)"
        ),
    )


@router.get("/list", response_model=list[dict[str, Any]])
def list_governance_parameters() -> list[dict[str, Any]]:
    """List parameters that can be changed via governance."""
    return [
        {"name": name, "type": typ.__name__, "description": f"Governance-controllable {name}"}
        for name, typ in GOVERNANCE_PARAMETERS.items()
    ]
