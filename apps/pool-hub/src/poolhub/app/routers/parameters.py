"""Governance-triggered parameter change router for pool hub (v0.7.4 §B3).

Provides an endpoint for the governance service to apply parameter changes
that have been approved via on-chain governance proposals. Validates that
the proposal ID is provided and the parameter change is well-formed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db_session as get_db
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


@router.post("/apply", response_model=ParameterChangeResponse)
async def apply_parameter_change(
    change: ParameterChangeRequest,
    db: Annotated[Session, Depends(get_db)],
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

    # Find the service config for the target service
    stmt = select(ServiceConfig).where(ServiceConfig.service_type == change.target_service)
    config = db.execute(stmt).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service config for '{change.target_service}' not found",
        )

    # Get old value for audit. Use getattr/setattr because SQLAlchemy Mapped
    # columns are typed as descriptors and direct attribute access confuses mypy.
    old_value: Any
    new_value: Any
    if change.parameter_name == "max_concurrent":
        new_value = cast(int, change.new_value)
        old_value = int(config.max_concurrent)
        config.max_concurrent = new_value
    elif change.parameter_name == "enabled":
        new_value = bool(change.new_value)
        old_value = bool(config.enabled)
        config.enabled = new_value
    elif change.parameter_name == "pricing":
        new_value = cast(dict[str, Any], change.new_value)
        old_value = dict(config.pricing)
        config.pricing = new_value
    elif change.parameter_name == "config":
        new_value = cast(dict[str, Any], change.new_value)
        old_value = dict(config.config)
        config.config = new_value
    elif change.parameter_name == "capabilities":
        new_value = cast(list[str], change.new_value)
        old_value = list(config.capabilities)
        config.capabilities = new_value
    else:
        # Should not reach here due to validation above
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parameter")

    # Validate old_value if provided
    if change.old_value is not None and old_value != change.old_value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expected old value {change.old_value!r} does not match actual {old_value!r}",
        )

    config.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(config)

    return ParameterChangeResponse(
        proposal_id=change.proposal_id,
        applied=True,
        parameter_name=change.parameter_name,
        old_value=old_value,
        new_value=change.new_value,
        applied_at=datetime.now(UTC).isoformat(),
        message=f"Parameter '{change.parameter_name}' updated for service '{change.target_service}'",
    )


@router.get("/list", response_model=list[dict[str, Any]])
async def list_governance_parameters() -> list[dict[str, Any]]:
    """List parameters that can be changed via governance."""
    return [
        {"name": name, "type": typ.__name__, "description": f"Governance-controllable {name}"}
        for name, typ in GOVERNANCE_PARAMETERS.items()
    ]
