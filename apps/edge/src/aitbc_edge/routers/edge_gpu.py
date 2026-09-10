"""Edge GPU wallet/balance router (placeholders).

The ``/balance`` and ``/transfer`` endpoints under ``/v1/edge-gpu`` are the
CLI-facing counterparts to ``aitbc edge balance`` and ``aitbc edge transfer``.
They are intentionally 501 for now; a future implementation can wire them to a
proper edge wallet without changing the CLI path.
"""

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/balance")
async def edge_gpu_balance() -> JSONResponse:
    """Placeholder for the edge GPU/wallet balance endpoint."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": "Not implemented",
            "detail": "Edge GPU balance is not yet implemented; use the wallet daemon or aitbc wallet commands.",
        },
    )


@router.post("/transfer")
async def edge_gpu_transfer(payload: dict[str, Any]) -> JSONResponse:
    """Placeholder for the edge GPU/wallet transfer endpoint."""
    _ = payload
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": "Not implemented",
            "detail": "Edge GPU transfer is not yet implemented; use aitbc wallet send.",
        },
    )
