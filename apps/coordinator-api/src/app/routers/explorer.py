from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from aitbc.rate_limiting import rate_limit

from ..schemas import (
    AddressListResponse,
    BlockListResponse,
    ReceiptListResponse,
    TransactionListResponse,
)
from ..services import ExplorerService
from ..storage import get_session

router = APIRouter(prefix="/explorer", tags=["explorer"])


def _service(session: Annotated[Session, Depends(get_session)]) -> ExplorerService:
    return ExplorerService(session)


@router.get("/blocks", response_model=BlockListResponse, summary="List recent blocks")
@rate_limit(rate=100, per=60)
async def list_blocks(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BlockListResponse:
    return _service(session).list_blocks(limit=limit, offset=offset)


@router.get(
    "/transactions",
    response_model=TransactionListResponse,
    summary="List recent transactions",
)
@rate_limit(rate=100, per=60)
async def list_transactions(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TransactionListResponse:
    return _service(session).list_transactions(limit=limit, offset=offset)


@router.get("/addresses", response_model=AddressListResponse, summary="List address summaries")
@rate_limit(rate=100, per=60)
async def list_addresses(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AddressListResponse:
    return _service(session).list_addresses(limit=limit, offset=offset)


@router.get("/receipts", response_model=ReceiptListResponse, summary="List job receipts")
@rate_limit(rate=100, per=60)
async def list_receipts(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    job_id: str | None = Query(default=None, description="Filter by job identifier"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReceiptListResponse:
    return _service(session).list_receipts(job_id=job_id, limit=limit, offset=offset)


@router.get("/transactions/{tx_hash}", summary="Get transaction details by hash")
@rate_limit(rate=100, per=60)
async def get_transaction(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    tx_hash: str,
) -> dict:
    """Get transaction details by hash from blockchain RPC"""
    return _service(session).get_transaction(tx_hash)
