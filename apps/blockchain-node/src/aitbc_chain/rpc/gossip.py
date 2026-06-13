"""
Gossip-related RPC endpoints.
"""


from fastapi import Request
from pydantic import BaseModel, Field
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..database import session_scope
from ..logger import get_logger
from ..models import Receipt
from .utils import get_chain_id

_logger = get_logger(__name__)


class GetLogsRequest(BaseModel):
    """Request model for eth_getLogs RPC endpoint."""
    address: str | None = Field(None, description="Contract address to filter logs")
    from_block: int | None = Field(None, description="Starting block height")
    to_block: int | None = Field(None, description="Ending block height")
    topics: list[str] | None = Field(None, description="Event topics to filter")


class LogEntry(BaseModel):
    """Single log entry from smart contract event."""
    address: str
    topics: list[str]
    data: str
    block_number: int
    transaction_hash: str
    log_index: int


class GetLogsResponse(BaseModel):
    """Response model for eth_getLogs RPC endpoint."""
    logs: list[LogEntry]
    count: int


@rate_limit(rate=200, per=60)
async def get_logs(
    request: Request,
    logs_request: GetLogsRequest,
    chain_id: str | None = None
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
            query = query.where(Receipt.block_height >= logs_request.from_block)  # type: ignore[operator]
        if logs_request.to_block is not None:
            query = query.where(Receipt.block_height <= logs_request.to_block)  # type: ignore[operator]

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
