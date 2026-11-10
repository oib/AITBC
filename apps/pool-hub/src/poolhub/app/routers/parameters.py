"""Governance-triggered parameter change router for pool hub (v0.7.4 §B3).

Provides an endpoint for the governance service to apply parameter changes
that have been approved via on-chain governance proposals. Validates that
the proposal ID is provided and the parameter change is well-formed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from aitbc.auth import APIKeyAuthenticator
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, select, update
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

# The service's own write path (ServiceConfigCreate/Update schemas) bounds
# max_concurrent to 1..10 — the governance apply must enforce the same
# invariant or a proposal could set 0 (drain capacity) or an out-of-range
# int that overflows the Integer column on PostgreSQL (#1421 second pass).
_MAX_CONCURRENT_MIN = 1
_MAX_CONCURRENT_MAX = 10


def _validate_parameter_value(parameter_name: str, new_value: Any) -> None:
    """Type-check a governance parameter value (#1500).

    bool is a subclass of int — a JSON `true` must not satisfy an int
    parameter, and a negative value is meaningless for the numeric
    governance parameters (currently only max_concurrent).
    """
    expected_type = GOVERNANCE_PARAMETERS[parameter_name]
    value_ok = isinstance(new_value, expected_type)
    if expected_type is int and (
        isinstance(new_value, bool)
        or not isinstance(new_value, int)
        or not (_MAX_CONCURRENT_MIN <= new_value <= _MAX_CONCURRENT_MAX)
    ):
        value_ok = False
    if expected_type is list and (not all(isinstance(item, str) for item in new_value)):
        # capabilities is list[str] on the service schema — a JSON list of
        # ints would pass isinstance(list) but violate the column contract.
        value_ok = False
    if not value_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter '{parameter_name}' expects type {expected_type.__name__}, got {type(new_value).__name__}",
        )


_governance_auth = APIKeyAuthenticator(
    expected_key=settings.coordinator_shared_secret,
    auth_enabled=True,
    header_name="X-PoolHub-Key",
    success_role="governance",
)


def _parameter_response(
    change: ParameterChangeRequest, config_count: int, old_vals: list[Any], note: str = ""
) -> ParameterChangeResponse:
    return ParameterChangeResponse(
        proposal_id=change.proposal_id,
        applied=True,
        parameter_name=change.parameter_name,
        old_value=old_vals[0] if len(old_vals) == 1 else old_vals,
        new_value=change.new_value,
        applied_at=datetime.now(UTC).isoformat(),
        message=(
            f"Parameter '{change.parameter_name}' updated for service "
            f"'{change.target_service}' on {config_count} miner config(s)" + note
        ),
    )


async def _write_parameter_value(
    db: AsyncSession,
    change: ParameterChangeRequest,
    configs: list[ServiceConfig],
    old_values: list[Any],
) -> ParameterChangeResponse:
    """Persist the validated new value, atomically checking old_value (#1600)."""
    now = datetime.now(UTC)
    column = getattr(ServiceConfig, change.parameter_name)
    if change.old_value is not None and not isinstance(column.type, JSON):
        # Atomic check-and-set (#1600): fold the old_value precondition into
        # the UPDATE's WHERE clause. old_values[0] is a genuine DB value (the
        # Python == check in the caller already proved every row equals
        # old_value), avoiding caller-side type coercion surprises
        # (1 == True, 1.0 == 1). A concurrent apply that already moved the
        # rows makes this match fewer rows than expected -> 409 and rollback
        # of the partial write.
        result = await db.execute(
            update(ServiceConfig)
            .where(
                ServiceConfig.id.in_([c.id for c in configs]),
                column == old_values[0],
            )
            .values({change.parameter_name: change.new_value, "updated_at": now})
        )
        if cast(Any, result).rowcount != len(configs):
            # The locked read above can be stale on engines without row
            # locks (SQLite). Re-read inside the write transaction: if every
            # row already holds new_value this was an idempotent replay;
            # otherwise a real conflict -> 409 and rollback of the partial
            # write.
            current = (await db.execute(select(column).where(ServiceConfig.id.in_([c.id for c in configs])))).scalars().all()
            if len(current) == len(configs) and all(v == change.new_value for v in current):
                await db.commit()
                return _parameter_response(
                    change, len(configs), old_values, "; already at requested value (idempotent replay)"
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Parameter '{change.parameter_name}' changed concurrently for service "
                    f"'{change.target_service}': expected old value {change.old_value!r} no longer holds"
                ),
            )
    # No baseline precondition, or a JSON column: PostgreSQL `json` has no
    # equality operator, so the guarded UPDATE cannot express the predicate —
    # the FOR UPDATE row locks above carry the guarantee there (on SQLite a
    # raced JSON apply is not pinned by tests).
    for config in configs:
        setattr(config, change.parameter_name, change.new_value)
        config.updated_at = now

    await db.commit()

    return _parameter_response(change, len(configs), old_values)


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

    _validate_parameter_value(change.parameter_name, change.new_value)

    # Governance changes are service-wide: ServiceConfig is keyed per-miner
    # (miner_id + service_type) and the request carries no miner_id, so the
    # change applies to every config row for the target service type.
    # with_for_update() row-locks the set on PostgreSQL so a concurrent apply
    # cannot slip a write between the old_value check and our UPDATE (#1600);
    # it is a no-op on SQLite, where the guarded UPDATE below is the atomic
    # check-and-set.
    stmt = select(ServiceConfig).where(ServiceConfig.service_type == change.target_service).with_for_update()
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

    mismatched = [v for v in old_values if change.old_value is not None and v != change.old_value]
    if mismatched:
        # Idempotent replay (#1600): if every row already sits at new_value
        # the apply already happened (e.g. a retry after a lost response, or
        # the loser of a concurrent pair re-reading post-commit state under
        # FOR UPDATE) — report success rather than a spurious 409.
        if all(v == change.new_value for v in old_values):
            return _parameter_response(change, len(configs), old_values, "; already at requested value (idempotent replay)")
        # old_value must match every miner's row, otherwise the
        # governance-approved baseline does not hold fleet-wide.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expected old value {change.old_value!r} does not match actual {mismatched[0]!r}",
        )

    return await _write_parameter_value(db, change, configs, old_values)


@router.get("/list", response_model=list[dict[str, Any]])
def list_governance_parameters() -> list[dict[str, Any]]:
    """List parameters that can be changed via governance."""
    return [
        {"name": name, "type": typ.__name__, "description": f"Governance-controllable {name}"}
        for name, typ in GOVERNANCE_PARAMETERS.items()
    ]
