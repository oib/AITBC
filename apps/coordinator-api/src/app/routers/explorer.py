from sqlalchemy.orm import Session
from typing import Annotated
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..schemas import (
    BlockListResponse,
    TransactionListResponse,
    AddressListResponse,
    ReceiptListResponse,
)
from ..services import ExplorerService
from ..storage import Annotated[Session, Depends(get_session)], get_session

router = APIRouter(prefix="/explorer", tags=["explorer"])


def _service(session: Annotated[Session, Depends(get_session)] = Depends()) -> ExplorerService:
    return ExplorerService(session)


@router.get("/blocks", response_model=BlockListResponse, summary="List recent blocks")
async def list_blocks(
    *,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BlockListResponse:
    return _service(session).list_blocks(limit=limit, offset=offset)


@router.get(
    "/transactions",
    response_model=TransactionListResponse,
    summary="List recent transactions",
)
async def list_transactions(
    *,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TransactionListResponse:
    return _service(session).list_transactions(limit=limit, offset=offset)


@router.get("/addresses", response_model=AddressListResponse, summary="List address summaries")
async def list_addresses(
    *,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AddressListResponse:
    return _service(session).list_addresses(limit=limit, offset=offset)


@router.get("/receipts", response_model=ReceiptListResponse, summary="List job receipts")
async def list_receipts(
    *,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    job_id: str | None = Query(default=None, description="Filter by job identifier"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReceiptListResponse:
    return _service(session).list_receipts(job_id=job_id, limit=limit, offset=offset)
