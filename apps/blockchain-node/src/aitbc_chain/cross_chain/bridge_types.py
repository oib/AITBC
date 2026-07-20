"""Cross-chain bridge shared types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


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
