"""Durable operation ledger for the coordinator's financial mutations.

Mirrors the market/wallet pattern: ``POST /payments``,
``/payments/{id}/release`` and ``/payments/{id}/refund`` bind an
``Idempotency-Key`` to one durable outcome. All three are
``allow_adopt=False`` — a retried release or refund cannot tell whether the
first attempt already settled on-chain, so ambiguous outcomes go
``uncertain`` (409 on replay) until the reconciler or an operator resolves
them, rather than silently re-driving a settlement.

The service layer's own state checks stay in place as the keyless-caller
backstop; the ledger adds replay-verbatim responses for callers that send a
key.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR
from aitbc.operations import BeginStatus, OperationLedger, request_hash

logger = get_logger(__name__)

_ledger: OperationLedger | None = None


def get_operations_ledger() -> OperationLedger:
    """The coordinator operations ledger (``coordinator_operations.db``)."""
    global _ledger
    if _ledger is None:
        path = os.getenv("COORDINATOR_OPERATIONS_DB") or str(DATA_DIR / "data" / "coordinator_operations.db")
        _ledger = OperationLedger(path, service="coordinator-api")
    return _ledger


async def begin_operation(
    request: Request | None, operation_type: str, payload: dict[str, Any], *, allow_adopt: bool = False
) -> tuple[str, int, JSONResponse | None]:
    """Dedupe a mutating request by its ``Idempotency-Key`` header.

    Returns ``(key, attempt, None)`` when the caller should execute, or
    ``(key, 0, response)`` when the ledger already has a verdict — replays
    return the originally recorded response verbatim; conflicts, in-flight
    duplicates and uncertain operations get distinct 409s.
    """
    key = ((request.headers.get("Idempotency-Key") if request is not None else "") or "").strip()
    if not key:
        return "", 0, None
    begin = await get_operations_ledger().begin_async(key, operation_type, request_hash(payload), allow_adopt=allow_adopt)
    if begin.status is BeginStatus.EXECUTE:
        return key, begin.attempt, None
    if begin.status is BeginStatus.REPLAY:
        return key, 0, JSONResponse(status_code=begin.response_status or 200, content=begin.result)
    detail = {
        BeginStatus.CONFLICT: "Idempotency-Key was already used with a different request",
        BeginStatus.UNCERTAIN: (
            "A previous attempt with this Idempotency-Key did not complete and its "
            "outcome is unknown; resolve it before retrying"
        ),
    }.get(begin.status, "A request with this Idempotency-Key is already in progress")
    return key, 0, JSONResponse(status_code=409, content={"error": detail})


async def record_rejection(key: str, attempt: int, status_code: int, content: dict[str, Any]) -> JSONResponse:
    """Memoize a deterministic rejection so a replay gets the first answer."""
    if key and attempt:
        await get_operations_ledger().complete_async(key, attempt, content, response_status=status_code)
    return JSONResponse(status_code=status_code, content=content)


async def complete_operation(key: str, attempt: int, result: Any, *, response_status: int = 200) -> None:
    if key and attempt:
        await get_operations_ledger().complete_async(key, attempt, result, response_status=response_status)


async def fail_operation(key: str, attempt: int, error: str) -> None:
    if key and attempt:
        try:
            await get_operations_ledger().fail_async(key, attempt, error)
        except Exception:
            logger.exception("Failed to record operation failure")
