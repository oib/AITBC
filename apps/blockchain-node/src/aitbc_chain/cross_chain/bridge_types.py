"""Cross-chain bridge shared types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# Exact detail string for the HTTP 503 every lock-request surface returns
# while ``settings.bridge_locks_paused`` is set, and the message of
# ``BridgeLocksPausedError`` at the ``initiate_transfer`` chokepoint.
BRIDGE_LOCKS_PAUSED_DETAIL = "Bridge paused: locks unavailable until validator attestation is live"


class BridgeLocksPausedError(ValueError):
    """A new bridge lock was attempted while locks are paused.

    ``ValueError`` subclass so callers that already map validation failures
    keep working — the REST surfaces translate it to 503 before this is
    ever raised across the request boundary.
    """


class BridgeStatus(Enum):
    """Status of a cross-chain transfer."""

    pending = "pending"
    locked = "locked"
    confirmed = "confirmed"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


@dataclass
class BridgeTransfer:
    """Cross-chain transfer record."""

    transfer_id: str
    source_chain: str
    target_chain: str
    sender: str
    recipient: str
    amount: int
    asset: str
    status: BridgeStatus
    source_tx_hash: str | None
    target_tx_hash: str | None
    lock_time: datetime | None
    confirm_time: datetime | None
    proof: dict[str, Any] | None
