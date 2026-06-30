# v0.8.0 Inter-Chain Trading Basics — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create a new `aitbc/trading/` package with inter-chain trade types, a TradingClient for the trading service REST API, and bridge integration utilities for cross-chain escrow operations. These are dependency-free shared types consumed by the trading service and CLI.

**Working directory**: `/opt/aitbc/aitbc/trading/`

**Prerequisite**: v0.7.0-v0.7.2 ✅ (bridge RPC endpoints available). v0.7.3 Agent A ✅ (governance SDK pattern established).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/trading/ tests/unit/test_trading_sdk.py && ./venv/bin/python -m pytest tests/unit/test_trading_sdk.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/trading/types.py` — InterChainTradeStatus enum, InterChainTradeData, ChainInfo, TradeMatchResult, TradingConfig | 🔴 P0 | `aitbc/trading/types.py` (new), `aitbc/trading/__init__.py` (new) | ✅ |
| A2 | Create `aitbc/trading/client.py` — TradingClient async HTTP client for trading service REST API | 🔴 P0 | `aitbc/trading/client.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A3 | Create `aitbc/trading/bridge.py` — bridge integration utilities (lock escrow, verify transfer, query balance/health) | 🔴 P0 | `aitbc/trading/bridge.py` (new), `aitbc/trading/__init__.py` (extend) | ✅ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_trading_sdk.py` (new) | ✅ |

---

## A1: Trading Types

Create `aitbc/trading/types.py`:

```python
class InterChainTradeStatus(StrEnum):
    """Status of an inter-chain trade."""
    PENDING = "pending"       # created, awaiting match
    MATCHED = "matched"       # match found, awaiting agreement
    LOCKED = "locked"         # escrow locked on source chain (v0.9.0)
    CONFIRMED = "confirmed"   # confirmed on dest chain (v0.9.0)
    COMPLETED = "completed"   # fully settled
    CANCELLED = "cancelled"   # cancelled by party
    FAILED = "failed"         # failed during lifecycle


@dataclass
class TradingConfig:
    """Configuration for inter-chain trading operations."""
    rpc_url: str = "http://localhost:8108"  # trading service port
    blockchain_rpc_url: str = "http://localhost:8202"  # blockchain node
    bridge_rpc_url: str = "http://localhost:8202"  # bridge (same as blockchain)
    chain_id: str = "ait-hub"
    matching_enabled: bool = True
    execution_timeout: int = 300  # seconds
    island_registry_sync_interval: int = 300  # seconds
    timeout: int = 30  # HTTP client timeout


@dataclass
class InterChainTradeData:
    """Payload for creating an inter-chain trade."""
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


@dataclass
class ChainInfo:
    """Information about a registered AITBC chain."""
    chain_id: str
    endpoint: str
    status: str = "active"  # active, inactive, syncing, degraded
    block_height: int = 0
    offers_count: int = 0
    registered_at: str = ""
    last_sync: str = ""


@dataclass
class TradeMatchResult:
    """Result of matching an inter-chain trade."""
    trade_id: str
    matched: bool
    match_score: float = 0.0
    matched_chain: str = ""
    matched_offer_id: str = ""
    price: float = 0.0
    quantity: int = 0
    reason: str = ""  # why not matched if matched=False
```

---

## A2: Trading Client

Create `aitbc/trading/client.py` — async HTTP client for the trading service, following the same pattern as `aitbc/bridge/client.py` and `aitbc/governance/client.py`:

```python
class TradingClient:
    """HTTP client for the trading service REST endpoints."""
    # Wraps: POST /v1/trading/inter-chain/create, GET /v1/trading/inter-chain,
    # GET /v1/trading/inter-chain/{id}, GET /v1/trading/inter-chain/{id}/status,
    # GET /v1/trading/chains, POST /v1/trading/chains/register,
    # GET /v1/trading/chains/{id}/health, GET /v1/trading/inter-chain/history
```

Methods: `create_trade`, `get_trade`, `list_trades`, `get_trade_status`, `list_chains`, `register_chain`, `get_chain_health`, `get_trade_history`.

---

## A3: Bridge Integration Utilities

Create `aitbc/trading/bridge.py` — wraps `BridgeClient` from `aitbc/bridge/` for trading-specific bridge operations:

```python
class TradingBridgeClient:
    """Bridge client wrapper for inter-chain trading operations."""
    # Uses BridgeClient under the hood
    # lock_escrow(source_chain, amount, sender, recipient) -> transfer_id
    # verify_transfer(transfer_id) -> transfer status dict
    # get_chain_balance(chain_id) -> balance dict
    # check_bridge_health() -> health dict
```

---

## A4: Unit Tests

`tests/unit/test_trading_sdk.py` — tests for all types, client (mocked httpx), and bridge utilities (mocked BridgeClient).

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.0 — Inter-Chain Trading Basics
**Agent**: Agent A (Shared Core)
