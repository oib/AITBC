"""Idempotency-Key dedupe helpers for the market service's mutating routes.

Extracted from ``main.py``. The durable ledger singleton
(``_operations_ledger`` / ``_get_operations_ledger``) stays in ``main`` —
the test-suite resets it through ``market_service.main._operations_ledger``
— and is bound here via :func:`bind_ledger_getter` when the app module is
assembled. This module deliberately never imports ``main``.
"""

import json
import sqlite3
from collections.abc import Callable
from decimal import InvalidOperation
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.operations import BeginStatus, OperationLedger, request_hash

# Keep the historic logger name: caplog filters and log-schema checks key on
# "market_service.main".
logger = get_logger("market_service.main")

# Expected failure surface for the best-effort fallbacks below: filesystem/OS
# and sqlite ledger errors, HTTP/RPC I/O (httpx), request/JSON/Decimal decode
# (ValueError/InvalidOperation), lazy imports, and data-shape errors.
# RuntimeError covers abort-style raises a handler re-aborts with; genuine
# BaseExceptions (incl. asyncio.CancelledError) still propagate (#1862).
_OPS_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    InvalidOperation,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    httpx.HTTPError,
    sqlite3.Error,
)


_ledger_getter: Callable[[], OperationLedger] | None = None


def bind_ledger_getter(getter: Callable[[], OperationLedger]) -> None:
    """Point this module at ``main._get_operations_ledger`` (called once at app assembly)."""
    global _ledger_getter
    _ledger_getter = getter


def _get_operations_ledger() -> OperationLedger:
    """Delegate to the canonical accessor in ``main``."""
    if _ledger_getter is None:
        raise RuntimeError("operations ledger getter is not bound")
    return _ledger_getter()


async def _begin_operation(
    request: Request, operation_type: str, payload: dict[str, Any], *, allow_adopt: bool = True
) -> tuple[str, int, JSONResponse | None]:
    """Dedupe a mutating request by its ``Idempotency-Key`` header.

    Returns (key, attempt, None) when the caller should execute, or
    (key, 0, response) when the ledger already has a verdict — replays return
    the originally recorded response verbatim; conflicts, in-flight
    duplicates and uncertain operations get distinct 409s.
    """
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        return "", 0, None
    begin = await _get_operations_ledger().begin_async(key, operation_type, request_hash(payload), allow_adopt=allow_adopt)
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


async def _reject_operation(key: str, attempt: int, response: JSONResponse) -> JSONResponse:
    """Record a deterministic rejection as the operation's result.

    The Idempotency-Key binds to whatever the first attempt answered — a
    replay of a rejected request gets the same rejection, not a re-check
    against mutated state. Takes the JSONResponse rather than parts so the
    literal ``JSONResponse(status_code=..., content=...)`` stays in the
    handler body, where the OpenAPI error-response extractor can see it.
    """
    if key and attempt:
        body = json.loads(bytes(response.body)) if response.body else None
        await _get_operations_ledger().complete_async(key, attempt, body, response_status=response.status_code)
    return response


async def _fail_operation(key: str, attempt: int, error: str, *, terminal: bool = False) -> None:
    """Mark an attempt failed after an unexpected exception."""
    if key and attempt:
        try:
            await _get_operations_ledger().fail_async(key, attempt, error, terminal=terminal)
        except _OPS_ERRORS:
            logger.error("Failed to record operation failure for key %s", key)
