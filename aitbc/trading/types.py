"""Shared inter-chain trading types for AITBC (v0.8.0 §A1).

These are the canonical shared SDK types for inter-chain trading between
AITBC blockchain networks (islands). They define the trade lifecycle
status, trade payload structures, chain registry entries, and matching
results used by the trading service (``apps/trading/``) and CLI.

The trading service runs on port 8104 (``TRADING_BIND_PORT`` env var,
verified in ``apps/trading/src/trading_service/main.py:469``). The
blockchain node RPC and bridge run on port 8202 (verified in
``aitbc/constants.py:50``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class InterChainTradeStatus(StrEnum):
    """Status of an inter-chain trade.

    The lifecycle is: pending → matched → locked → confirmed → completed.
    Any state can transition to cancelled or failed.

    - ``pending``: trade created, awaiting match
    - ``matched``: match found, awaiting agreement
    - ``locked``: escrow locked on source chain (v0.9.0)
    - ``confirmed``: confirmed on dest chain (v0.9.0)
    - ``completed``: fully settled
    - ``cancelled``: cancelled by a party
    - ``failed``: failed during lifecycle
    """

    PENDING = "pending"
    MATCHED = "matched"
    LOCKED = "locked"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SettlementPhase(StrEnum):
    """Settlement phase for an inter-chain trade (v0.9.0).

    Tracks the atomic settlement progress separately from the trade
    status. A trade can be ``completed`` (trade delivered) but still
    in ``settling`` phase (escrow not yet released).

    - ``none``: no settlement initiated (trade not yet locked)
    - ``escrow_created``: escrow record created, HTLC params generated
    - ``escrow_locked``: funds locked on source chain (HTLC funded)
    - ``lock_verified``: lock proof verified on destination chain
    - ``trade_executed``: trade executed on destination chain
    - ``settled``: both chains settled atomically (terminal)
    - ``refunded``: both chains refunded after timeout (terminal)
    - ``disputed``: under dispute resolution
    """

    NONE = "none"
    ESCROW_CREATED = "escrow_created"
    ESCROW_LOCKED = "escrow_locked"
    LOCK_VERIFIED = "lock_verified"
    TRADE_EXECUTED = "trade_executed"
    SETTLED = "settled"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class ChainStatus(StrEnum):
    """Status of a registered AITBC chain in the island registry."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SYNCING = "syncing"
    DEGRADED = "degraded"


@dataclass
class TradingConfig:
    """Configuration for inter-chain trading operations.

    The trading service runs on port 8104 (``TRADING_BIND_PORT``, verified
    in ``main.py:469``). The blockchain node RPC and bridge both run on
    port 8202 (verified in ``aitbc/constants.py:50`` and
    ``apps/blockchain-node/src/aitbc_chain/config.py:89``).
    """

    rpc_url: str = "http://localhost:8104"  # trading service
    blockchain_rpc_url: str = "http://localhost:8202"  # blockchain node
    bridge_rpc_url: str = "http://localhost:8202"  # bridge (same as blockchain)
    chain_id: str = "ait-hub"
    matching_enabled: bool = True
    execution_timeout: int = 300  # seconds
    island_registry_sync_interval: int = 300  # seconds
    timeout: int = 30  # HTTP client timeout


@dataclass
class InterChainTradeData:
    """Payload for creating an inter-chain trade.

    This dataclass mirrors the fields stored in the trading service's
    ``InterChainTrade`` SQLModel (Agent B B2) but is dependency-free for
    use by the CLI and other services.
    """

    trade_id: str
    source_chain: str
    dest_chain: str
    sender: str
    recipient: str
    amount: int
    offer_id: str | None = None
    price: float = 0.0
    quantity: int = 0
    status: str = "pending"
    source_tx_hash: str | None = None
    dest_tx_hash: str | None = None
    chain_id: str = "ait-hub"
    # v0.9.0 settlement fields
    escrow_id: str = ""
    settlement_phase: str = "none"  # SettlementPhase value
    secret_hash: str = ""
    source_timelock: int = 0
    dest_timelock: int = 0


@dataclass
class ChainInfo:
    """Information about a registered AITBC chain.

    Mirrors the ``IslandRegistryEntry`` SQLModel (Agent B B2) for use by
    the CLI and other services.
    """

    chain_id: str
    endpoint: str
    status: str = "active"
    block_height: int = 0
    offers_count: int = 0
    registered_at: str = ""
    last_sync: str = ""


@dataclass
class TradeMatchResult:
    """Result of matching an inter-chain trade.

    Returned by the matching engine (Agent B B6) when a trade is matched
    against available offers across chains.
    """

    trade_id: str
    matched: bool
    match_score: float = 0.0
    matched_chain: str = ""
    matched_offer_id: str = ""
    price: float = 0.0
    quantity: int = 0
    reason: str = ""


@dataclass
class TradeHistoryEntry:
    """A single entry in the inter-chain trade history.

    Used for audit trail and analytics across chains.
    """

    trade_id: str
    source_chain: str
    dest_chain: str
    status: str
    amount: int
    price: float = 0.0
    quantity: int = 0
    created_at: str = ""
    completed_at: str = ""
    source_tx_hash: str | None = None
    dest_tx_hash: str | None = None


@dataclass
class CreateTradeRequest:
    """Request to create a new inter-chain trade.

    Used by the CLI and TradingClient to submit a trade creation request
    to the trading service.
    """

    source_chain: str
    dest_chain: str
    sender: str
    recipient: str
    amount: int
    offer_id: str | None = None
    price: float = 0.0
    quantity: int = 0
    chain_id: str = "ait-hub"


@dataclass
class RegisterChainRequest:
    """Request to register a new chain in the island registry."""

    chain_id: str
    endpoint: str
    chain_id_field: str = field(default="")  # alias for clarity in JSON

    def to_dict(self) -> dict[str, str]:
        """Serialize to a dict for JSON transport."""
        return {
            "chain_id": self.chain_id,
            "endpoint": self.endpoint,
        }
