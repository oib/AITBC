"""
Gossip-related RPC endpoints.
"""

from typing import List, Optional
from fastapi import Request
from pydantic import BaseModel, Field
from sqlmodel import select

from ..database import session_scope
from ..models import Receipt
from ..logger import get_logger
from .utils import get_chain_id
from aitbc.rate_limiting import rate_limit

_logger = get_logger(__name__)


class GetLogsRequest(BaseModel):
    """Request model for eth_getLogs RPC endpoint."""
    address: Optional[str] = Field(None, description="Contract address to filter logs")
    from_block: Optional[int] = Field(None, description="Starting block height")
    to_block: Optional[int] = Field(None, description="Ending block height")
    topics: Optional[List[str]] = Field(None, description="Event topics to filter")


class LogEntry(BaseModel):
    """Single log entry from smart contract event."""
    address: str
    topics: List[str]
    data: str
    block_number: int
    transaction_hash: str
    log_index: int


class GetLogsResponse(BaseModel):
    """Response model for eth_getLogs RPC endpoint."""
    logs: List[LogEntry]
    count: int


@rate_limit(rate=200, per=60)
async def get_logs(
    request: Request,
    logs_request: GetLogsRequest,
    chain_id: Optional[str] = None
) -> GetLogsResponse:
    """
    Query smart contract event logs using eth_getLogs-compatible endpoint.
    Filters Receipt model for logs matching contract address and event topics.
    """
    chain_id = get_chain_id(chain_id)

    with session_scope() as session:
        # Build query for receipts
        query = select(Receipt).where(Receipt.chain_id == chain_id)

        # Filter by block range
        if logs_request.from_block is not None:
            query = query.where(Receipt.block_height >= logs_request.from_block)
        if logs_request.to_block is not None:
            query = query.where(Receipt.block_height <= logs_request.to_block)

        # Execute query
        receipts = session.execute(query).scalars().all()

        logs = []
        for receipt in receipts:
            # Extract event logs from receipt payload
            payload = receipt.payload or {}
            events = payload.get("events", [])

            for event in events:
                # Filter by contract address if specified
                if logs_request.address and event.get("address") != logs_request.address:
                    continue

                # Filter by topics if specified
                if logs_request.topics:
                    event_topics = event.get("topics", [])
                    if not any(topic in event_topics for topic in logs_request.topics):
                        continue

                # Create log entry
                log_entry = LogEntry(
                    address=event.get("address", ""),
                    topics=event.get("topics", []),
                    data=str(event.get("data", "")),
                    block_number=receipt.block_height or 0,
                    transaction_hash=receipt.receipt_id,
                    log_index=event.get("logIndex", 0)
                )
                logs.append(log_entry)

        return GetLogsResponse(logs=logs, count=len(logs))
