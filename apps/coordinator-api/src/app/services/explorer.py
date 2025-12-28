from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..domain import Job, JobReceipt
from ..schemas import (
    BlockListResponse,
    BlockSummary,
    TransactionListResponse,
    TransactionSummary,
    AddressListResponse,
    AddressSummary,
    ReceiptListResponse,
    ReceiptSummary,
    JobState,
)

_STATUS_LABELS = {
    JobState.queued: "Queued",
    JobState.running: "Running",
    JobState.completed: "Succeeded",
    JobState.failed: "Failed",
    JobState.canceled: "Canceled",
    JobState.expired: "Expired",
}

_DEFAULT_HEIGHT_BASE = 100_000


class ExplorerService:
    """Derives explorer-friendly summaries from coordinator data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_blocks(self, *, limit: int = 20, offset: int = 0) -> BlockListResponse:
        statement = select(Job).order_by(Job.requested_at.desc())
        jobs = self.session.exec(statement.offset(offset).limit(limit)).all()

        items: list[BlockSummary] = []
        for index, job in enumerate(jobs):
            height = _DEFAULT_HEIGHT_BASE + offset + index
            proposer = job.assigned_miner_id or "unassigned"
            items.append(
                BlockSummary(
                    height=height,
                    hash=job.id,
                    timestamp=job.requested_at,
                    tx_count=1,
                    proposer=proposer,
                )
            )

        next_offset: Optional[int] = offset + len(items) if len(items) == limit else None
        return BlockListResponse(items=items, next_offset=next_offset)

    def list_transactions(self, *, limit: int = 50, offset: int = 0) -> TransactionListResponse:
        statement = (
            select(Job)
            .order_by(Job.requested_at.desc())
            .offset(offset)
            .limit(limit)
        )
        jobs = self.session.exec(statement).all()

        items: list[TransactionSummary] = []
        for index, job in enumerate(jobs):
            height = _DEFAULT_HEIGHT_BASE + offset + index
            status_label = _STATUS_LABELS.get(job.state, job.state.value.title())
            value = job.payload.get("value") if isinstance(job.payload, dict) else None
            if value is None:
                value_str = "0"
            elif isinstance(value, (int, float)):
                value_str = f"{value}"
            else:
                value_str = str(value)

            items.append(
                TransactionSummary(
                    hash=job.id,
                    block=height,
                    from_address=job.client_id,
                    to_address=job.assigned_miner_id,
                    value=value_str,
                    status=status_label,
                )
            )

        next_offset: Optional[int] = offset + len(items) if len(items) == limit else None
        return TransactionListResponse(items=items, next_offset=next_offset)

    def list_addresses(self, *, limit: int = 50, offset: int = 0) -> AddressListResponse:
        statement = select(Job).order_by(Job.requested_at.desc())
        jobs = self.session.exec(statement.offset(offset).limit(limit)).all()

        address_map: dict[str, dict[str, object]] = defaultdict(
            lambda: {
                "address": "",
                "balance": "0",
                "tx_count": 0,
                "last_active": datetime.min,
                "recent_transactions": deque(maxlen=5),
            }
        )

        def touch(address: Optional[str], tx_id: str, when: datetime, value_hint: Optional[str] = None) -> None:
            if not address:
                return
            entry = address_map[address]
            entry["address"] = address
            entry["tx_count"] = int(entry["tx_count"]) + 1
            if when > entry["last_active"]:
                entry["last_active"] = when
            if value_hint:
                entry["balance"] = value_hint
            recent: deque[str] = entry["recent_transactions"]  # type: ignore[assignment]
            recent.appendleft(tx_id)

        for job in jobs:
            value = job.payload.get("value") if isinstance(job.payload, dict) else None
            value_hint: Optional[str] = None
            if value is not None:
                value_hint = str(value)
            touch(job.client_id, job.id, job.requested_at, value_hint=value_hint)
            touch(job.assigned_miner_id, job.id, job.requested_at)

        sorted_addresses = sorted(
            address_map.values(),
            key=lambda entry: entry["last_active"],
            reverse=True,
        )

        sliced = sorted_addresses[offset : offset + limit]
        items = [
            AddressSummary(
                address=entry["address"],
                balance=str(entry["balance"]),
                txCount=int(entry["tx_count"]),
                lastActive=entry["last_active"],
                recentTransactions=list(entry["recent_transactions"]),
            )
            for entry in sliced
        ]

        next_offset: Optional[int] = offset + len(sliced) if len(sliced) == limit else None
        return AddressListResponse(items=items, next_offset=next_offset)

    def list_receipts(
        self,
        *,
        job_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReceiptListResponse:
        statement = select(JobReceipt).order_by(JobReceipt.created_at.desc())
        if job_id:
            statement = statement.where(JobReceipt.job_id == job_id)

        rows = self.session.exec(statement.offset(offset).limit(limit)).all()
        items: list[ReceiptSummary] = []
        for row in rows:
            payload = row.payload or {}
            miner = payload.get("miner") or payload.get("miner_id") or "unknown"
            coordinator = payload.get("coordinator") or payload.get("coordinator_id") or "unknown"
            status = payload.get("status") or payload.get("state") or "Unknown"
            items.append(
                ReceiptSummary(
                    receipt_id=row.receipt_id,
                    miner=miner,
                    coordinator=coordinator,
                    issued_at=row.created_at,
                    status=status,
                    payload=payload,
                )
            )

        resolved_job_id = job_id or "all"
        return ReceiptListResponse(job_id=resolved_job_id, items=items)
