# v0.8.0 — Agent Task Assignment

**Release Theme**: Inter-Chain Trading Basics — Island Registry, Chain Discovery, Inter-Chain Trade Requests, Basic Matching

**Goal**: Extend the existing `apps/trading/` service (1011 lines, P2P agent-to-agent) with inter-chain trading capabilities: InterChainTrade schema, island registry, chain discovery, inter-chain trade lifecycle, basic matching engine, CLI commands. Defer atomic cross-chain settlement to v0.9.0 and cross-chain offer sync to v0.8.1.

> **Rescope from original change.log**: The original v0.8.0 change.log claimed "No trading service exists" — this is **FALSE**. `apps/trading/` exists with 1011 lines (FastAPI app, domain models, service layer, SQLite storage). However, it only has P2P agent-to-agent models (TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement, TradeFeedback) with NO inter-chain fields (source_chain, dest_chain). v0.8.0 extends this existing service with inter-chain capabilities rather than creating a new app from scratch.

> **Prerequisite correction**: The user's analysis claimed v0.7.1 and v0.7.2 are "not done" — this is **FALSE**. Both are complete and committed:
> - v0.7.1 (Bridge Security): Agent A `1fcf1e829` + Agent B `a4ea61295` — multi-sig, validator sets, block header sigs, CLI commands
> - v0.7.2 (Bridge Verification): Agent A `9a7b17a34` + Agent B `09fa64342` — Merkle proofs, block headers, finality, oracle status, release unfenced
> - Bridge release is now **unfenced** (`bridge_release_enabled: bool = True` in `config.py:292`)
> - All 15 bridge RPC endpoints are operational (lock, confirm, unlock, transfer, pending, balance, health, batch, validators, security, block-headers, oracle)

> **Stale port correction**: The change.log migration guide references `BLOCKCHAIN_RPC_URL=http://localhost:8006`. Port 8006 is stale — the correct port is **8202** (verified in `aitbc/constants.py:50` and `apps/blockchain-node/src/aitbc_chain/config.py:89`).

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅, [v0.6.3](../v0.6.3/change.log) ✅, [v0.6.4](../v0.6.4/change.log) ✅, [v0.6.6](../v0.6.6/change.log) ✅, [v0.6.7](../v0.6.7/change.log) ✅.

> **Risk**: Medium. The existing trading service is SQLite-based and P2P-only. Adding inter-chain fields and bridge integration is additive (new tables, new endpoints, new client). The main risk is the matching engine across chains (price-time priority with chain-aware routing). No consensus-critical path is touched — trading is an off-chain service that submits transactions to the blockchain node via RPC.

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.8.0 Target |
|-----------|----------|---------------|---------------|
| **Trading service** | `apps/trading/src/trading_service/` (1011 lines) | ✅ EXISTS — FastAPI app, domain models, service layer, SQLite storage | Extend with inter-chain trade models, bridge client, chain discovery |
| **Domain models** | `domain/trading.py` (369 lines) | ✅ EXISTS — TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement, TradeFeedback (P2P agent-to-agent, NO chain fields) | Add InterChainTrade + IslandRegistry SQLModel tables |
| **Service layer** | `services/trading_service.py` (133 lines) | ✅ EXISTS — CRUD for requests, matches, agreements | Add inter-chain trade CRUD, chain discovery, matching engine |
| **FastAPI app** | `main.py` (471 lines) | ✅ EXISTS — 20+ endpoints (requests, matches, agreements, analytics, transactions, blocks, receipts) | Add inter-chain trade endpoints, chain registry endpoints |
| **Storage** | `storage.py` (38 lines) | ⚠️ SQLite (`sqlite+aiosqlite:///`) — no PostgreSQL | Keep SQLite for dev; add PostgreSQL support via DATABASE_URL env var (already supported) |
| **Trading config** | — | ❌ NONE — no Settings/BaseSettings, no blockchain_rpc_url, no bridge_rpc_url, no chain_id | Create Settings class with blockchain_rpc_url (8202), bridge_rpc_url (8202), default_chain_id, matching params |
| **Blockchain/bridge RPC client** | — | ❌ NONE — no AITBCHTTPClient, no BlockchainRPCClient, no BridgeClient | Add blockchain + bridge RPC client for chain health, balance queries, bridge lock/confirm |
| **InterChainTrade schema** | — | ❌ NOT DEFINED — no SQLModel class anywhere in codebase | Define InterChainTrade SQLModel (source_chain, dest_chain, status, source_tx_hash, dest_tx_hash, amount, sender, recipient) |
| **IslandRegistry table** | — | ❌ NOT a SQLModel table — `aitbc/network/island_registry.py` is a config string parser (104 lines), `cli/config_data/chains.py` is a CLI registry (122 lines) | Add IslandRegistry SQLModel table for persistent chain registry |
| **CLI trade commands** | `cli/aitbc_cli/commands/` | ❌ NONE — no `trade.py` (exchange/trading.py is for external exchanges) | Add `trade` command group (create, list, chains, get, status, register-chain, health, history) |
| **Bridge RPC endpoints** | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py` | ✅ 15 endpoints available (lock, confirm, unlock, transfer, pending, balance, health, batch, validators, security, block-headers, oracle) | Trading service calls these for inter-chain escrow (v0.9.0 does atomic settlement) |
| **Exchange app** | `apps/exchange/cross_chain_exchange.py` (457 lines) | ⚠️ EXISTS but SQLite-only with mock chain operations (asyncio.sleep + fake tx hashes), no blockchain-node RPC | NOT a v0.8.0 target — separate app, mock-based, will be deprecated or migrated in a future release |
| **Coordinator-API trading** | `apps/coordinator-api/src/app/contexts/trading/` (12,967 lines) | ✅ EXISTS — P2P trading with matching engine, AMM, pricing models | NOT a v0.8.0 target — separate bounded context, agent-to-agent same-chain |
| **Matching engine** | — | ❌ NONE in apps/trading/ — coordinator-api has P2PTradingProtocol but it's same-chain | Add basic inter-chain matching (price-time priority across chains) |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Trading service exists** — `apps/trading/` with 1011 lines, FastAPI app, systemd service, wrapper script
2. ✅ **P2P domain models complete** — TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement, TradeFeedback
3. ✅ **20+ API endpoints exist** — requests, matches, agreements, analytics, transactions, blocks, receipts
4. ✅ **Bridge RPC endpoints available** — 15 endpoints (lock, confirm, unlock, transfer, pending, balance, health, batch, validators, security, block-headers, oracle)
5. ✅ **v0.7.0-v0.7.2 complete** — bridge basics + security (multi-sig, validator sets, block sigs) + verification (Merkle proofs, finality, oracle)
6. ✅ **Bridge release unfenced** — `bridge_release_enabled: bool = True`
7. ✅ **Island registry config parser exists** — `aitbc/network/island_registry.py` (104 lines, parses ISLAND_REGISTRY env var)
8. ✅ **CLI chain registry exists** — `cli/config_data/chains.py` (122 lines, ChainRegistry class)
9. ✅ **Pool Hub exists** — v0.6.7 complete (`5bb3803bd`)
10. ✅ **Marketplace exists** — v0.6.6 complete with BlockchainRPCClient integration

### Architecture: Inter-Chain Trading (v0.8.0)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/trading/ — NEW PACKAGE)                           │
│                                                                      │
│  Trading types (A1 — NEW types.py):                                  │
│    InterChainTradeStatus enum — pending, matched, locked,            │
│      confirmed, completed, cancelled, failed                         │
│    InterChainTradeData — on-chain trade payload dataclass            │
│    ChainInfo — chain registry entry (chain_id, endpoint, status,     │
│      block_height, offers_count)                                     │
│    TradeMatchResult — matching result (trade_id, match_score,        │
│      matched_chain, price, quantity)                                 │
│    TradingConfig — rpc_url (trading service), blockchain_rpc_url     │
│      (8202), bridge_rpc_url (8202), chain_id, matching params        │
│                                                                      │
│  Trading client (A2 — NEW client.py):                                │
│    TradingClient — async HTTP client for trading service REST API    │
│    create_trade, get_trade, list_trades, get_status, list_chains,    │
│    register_chain, get_chain_health, get_trade_history               │
│                                                                      │
│  Bridge integration (A3 — NEW bridge.py):                            │
│    lock_escrow(source_chain, amount, sender, recipient) — bridge lock│
│    verify_transfer(transfer_id) — check bridge transfer status       │
│    get_chain_balance(chain_id) — query bridge balance per chain      │
│    check_bridge_health() — bridge health check                       │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Trading Service                      │
│                         │    │ (apps/trading/)                      │
│  trade create           │    │                                      │
│  trade list             │    │  Config (B1):                        │
│  trade chains           │    │    Settings class (blockchain_rpc_url,│
│  trade get              │    │    bridge_rpc_url, chain_id, matching)│
│  trade status           │    │                                      │
│  trade register-chain   │    │  Domain models (B2):                 │
│  trade health           │    │    InterChainTrade SQLModel           │
│  trade history          │    │    IslandRegistry SQLModel            │
│                         │    │    Alembic migration                 │
│  Uses TradingClient     │    │                                      │
│  (A2) + shared types    │    │  Blockchain/bridge client (B3):      │
│                         │    │    BlockchainRPCClient → query health │
│                         │    │    BridgeClient → lock/confirm/status│
│                         │    │                                      │
│                         │    │  Chain discovery (B4):               │
│                         │    │    Island registry sync loop         │
│                         │    │    Chain health monitoring           │
│                         │    │    Register/list/health endpoints    │
│                         │    │                                      │
│                         │    │  Inter-chain trade lifecycle (B5):   │
│                         │    │    Create → list → get → status      │
│                         │    │    History endpoint                  │
│                         │    │                                      │
│                         │    │  Matching engine (B6):               │
│                         │    │    Price-time priority across chains │
│                         │    │                                      │
│                         │    │  Tests (B8):                         │
│                         │    │    Trade lifecycle + chain discovery │
└─────────────────────────┘    └──────────────────────────────────────┘

  Blockchain Node (apps/blockchain-node/) — NOT modified in v0.8.0:
    Bridge RPC endpoints already available (v0.7.0-v0.7.2)
    Trading service calls these via BridgeClient (A3)
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/trading/` (new package), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/trading/src/`, `cli/aitbc_cli/commands/trade.py` (new), `apps/trading/tests/` |

**Conflict boundary**: Agent A owns `aitbc/trading/` package (new). Agent B owns `apps/trading/`, `cli/`. Agent B consumes Agent A's `TradingClient`, trading types, and bridge integration utilities. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3 (B3-B6 depend on A1 types + A3 bridge utilities). B1 (config) and B2 (domain models) can proceed in parallel with Agent A.

---

## Agent A — Shared Core

**Scope**: Create a new `aitbc/trading/` package with inter-chain trade types, a TradingClient for the trading service REST API, and bridge integration utilities for cross-chain escrow operations. These are dependency-free shared types consumed by the trading service and CLI.

**Working directory**: `/opt/aitbc/aitbc/trading/`

**Prerequisite**: v0.7.0-v0.7.2 ✅ (bridge RPC endpoints available). v0.7.3 Agent A ✅ (governance SDK pattern established).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/trading/ tests/unit/test_trading_sdk.py && ./venv/bin/python -m pytest tests/unit/test_trading_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/trading/types.py` — InterChainTradeStatus enum, InterChainTradeData, ChainInfo, TradeMatchResult, TradingConfig | 🔴 P0 | `aitbc/trading/types.py` (new), `aitbc/trading/__init__.py` (new) | ⬜ |
| A2 | Create `aitbc/trading/client.py` — TradingClient async HTTP client for trading service REST API | 🔴 P0 | `aitbc/trading/client.py` (new), `aitbc/trading/__init__.py` (extend) | ⬜ |
| A3 | Create `aitbc/trading/bridge.py` — bridge integration utilities (lock escrow, verify transfer, query balance/health) | 🔴 P0 | `aitbc/trading/bridge.py` (new), `aitbc/trading/__init__.py` (extend) | ⬜ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_trading_sdk.py` (new) | ⬜ |

### Agent A — Detailed Instructions

#### A1: Trading Types

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

#### A2: Trading Client

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

#### A3: Bridge Integration Utilities

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

#### A4: Unit Tests

`tests/unit/test_trading_sdk.py` — tests for all types, client (mocked httpx), and bridge utilities (mocked BridgeClient).

---

## Agent B — Apps & Infrastructure

**Scope**: Add trading service Settings class, InterChainTrade + IslandRegistry SQLModel tables, blockchain/bridge RPC client, chain discovery, inter-chain trade lifecycle endpoints, basic matching engine, CLI commands, integration tests.

**Working directory**: `/opt/aitbc/apps/trading/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A3 complete. v0.7.0-v0.7.2 complete (bridge RPC endpoints available).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/trading/src/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/trading/src:aitbc ./venv/bin/python -m pytest apps/trading/tests/test_v080_inter_chain.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add trading service Settings class (blockchain_rpc_url, bridge_rpc_url, chain_id, matching params) | 🔴 P0 | `apps/trading/src/trading_service/config.py` (new) | ⬜ |
| B2 | Add InterChainTrade + IslandRegistry SQLModel tables + Alembic migration | 🔴 P0 | `apps/trading/src/trading_service/domain/inter_chain.py` (new), `apps/trading/alembic/versions/` (new) | ⬜ |
| B3 | Add blockchain/bridge RPC client to trading service | 🔴 P0 | `apps/trading/src/trading_service/clients/blockchain.py` (new), `apps/trading/src/trading_service/clients/bridge.py` (new) | ⬜ |
| B4 | Chain discovery — island registry sync, chain health monitoring, register/list/health endpoints | 🔴 P0 | `apps/trading/src/trading_service/services/chain_discovery.py` (new), `main.py` (extend) | ⬜ |
| B5 | Inter-chain trade lifecycle — create, list, get, status, history endpoints | 🔴 P0 | `apps/trading/src/trading_service/services/inter_chain_service.py` (new), `main.py` (extend) | ⬜ |
| B6 | Basic matching engine (price-time priority across chains) | High | `apps/trading/src/trading_service/services/matching_engine.py` (new) | ⬜ |
| B7 | CLI trade command group | 🔴 P0 | `cli/aitbc_cli/commands/trade.py` (new), `cli/aitbc_cli/core/main.py` (extend) | ⬜ |
| B8 | Integration tests | High | `apps/trading/tests/test_v080_inter_chain.py` (new) | ⬜ |

### Agent B — Detailed Instructions

#### B1: Trading Service Config

Create `apps/trading/src/trading_service/config.py`:
```python
class Settings(BaseSettings):
    blockchain_rpc_url: str = "http://localhost:8202"  # NOT 8006
    bridge_rpc_url: str = "http://localhost:8202"  # bridge is on blockchain node
    default_chain_id: str = "ait-hub"
    matching_enabled: bool = True
    execution_timeout: int = 300
    island_registry_sync_interval: int = 300
    # Trading service port (check systemd service for actual port)
```

Note: The trading service port needs to be verified from the systemd service file. The `aitbc-trading.service` file exists but does not specify a port — check `main.py` for the uvicorn port.

#### B2: Inter-Chain Domain Models

Create `apps/trading/src/trading_service/domain/inter_chain.py`:
```python
class InterChainTrade(SQLModel, table=True):
    """Inter-chain trade between AITBC chains."""
    __tablename__ = "inter_chain_trades"
    trade_id: str = Field(primary_key=True, default_factory=lambda: f"trade_{uuid4().hex[:8]}")
    source_chain: str = Field(index=True)
    dest_chain: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    sender: str = Field(index=True)
    recipient: str
    amount: int
    offer_id: str | None = None
    price: float = 0.0
    quantity: int = 0
    source_tx_hash: str | None = None
    dest_tx_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class IslandRegistryEntry(SQLModel, table=True):
    """Registry of known AITBC chains for inter-chain trading."""
    __tablename__ = "island_registry"
    chain_id: str = Field(primary_key=True)
    endpoint: str
    status: str = Field(default="active", index=True)
    block_height: int = 0
    offers_count: int = 0
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_sync: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Add Alembic migration under `apps/trading/alembic/versions/`.

#### B3: Blockchain/Bridge RPC Client

Create `apps/trading/src/trading_service/clients/blockchain.py` — wraps `AITBCHTTPClient` for:
- `get_chain_health(chain_id)` → `GET /rpc/health`
- `get_block_height(chain_id)` → `GET /rpc/chain/{chain_id}/height`
- `get_account_balance(address)` → `GET /rpc/account/{address}`

Create `apps/trading/src/trading_service/clients/bridge.py` — wraps `BridgeClient` from `aitbc.bridge` for:
- `lock_escrow(source_chain, amount, sender, recipient)` → `POST /bridge/lock`
- `get_transfer_status(transfer_id)` → `GET /bridge/transfer/{id}`
- `get_chain_balance(chain_id)` → `GET /bridge/balance/{chain_id}`
- `check_health()` → `GET /bridge/health`

#### B4: Chain Discovery

Create `apps/trading/src/trading_service/services/chain_discovery.py`:
- `sync_island_registry()` — periodically poll registered chains' `/rpc/health`, update block_height + status
- `register_chain(chain_id, endpoint)` — add to IslandRegistry table
- `list_chains()` — list all registered chains with status
- `get_chain_health(chain_id)` — query chain's blockchain node RPC for health metrics

Add endpoints to `main.py`:
- `GET /v1/trading/chains` — list registered chains
- `POST /v1/trading/chains/register` — register a new chain
- `GET /v1/trading/chains/{chain_id}/health` — get chain health

#### B5: Inter-Chain Trade Lifecycle

Create `apps/trading/src/trading_service/services/inter_chain_service.py`:
- `create_trade(source_chain, dest_chain, sender, recipient, amount, offer_id, price, quantity)` — create InterChainTrade record
- `get_trade(trade_id)` — get trade by ID
- `list_trades(status, source_chain, dest_chain, limit, offset)` — list with filters
- `get_trade_status(trade_id)` — get trade status
- `get_trade_history(source_chain, dest_chain, limit)` — trade history across chains

Add endpoints to `main.py`:
- `POST /v1/trading/inter-chain/create` — create inter-chain trade
- `GET /v1/trading/inter-chain` — list inter-chain trades
- `GET /v1/trading/inter-chain/{trade_id}` — get trade details
- `GET /v1/trading/inter-chain/{trade_id}/status` — get trade status
- `GET /v1/trading/inter-chain/history` — get trade history

Note: Escrow locking and settlement are deferred to v0.9.0. v0.8.0 only handles create → match → agree lifecycle.

#### B6: Basic Matching Engine

Create `apps/trading/src/trading_service/services/matching_engine.py`:
- `match_trade(trade_id)` — find matching offers across chains (price-time priority)
- Price-time priority: highest price first, then earliest creation time
- Cross-chain: match trades where source_chain ≠ dest_chain
- Return `TradeMatchResult` (from A1 types)

#### B7: CLI Trade Commands

Create `cli/aitbc_cli/commands/trade.py` — follow the `bridge.py` pattern:
- `aitbc trade create --source-chain <chain> --dest-chain <chain> --amount <int> --sender <addr> --recipient <addr>` — create inter-chain trade
- `aitbc trade list [--status <status>] [--source-chain <chain>] [--dest-chain <chain>]` — list trades
- `aitbc trade chains` — list available chains
- `aitbc trade get <trade_id>` — get trade details
- `aitbc trade status --trade-id <id>` — get trade status
- `aitbc trade register-chain --chain-id <id> --endpoint <url>` — register new chain
- `aitbc trade health --chain-id <id>` — check chain health
- `aitbc trade history --source-chain <chain> --dest-chain <chain>` — view cross-chain history

Register in `cli/aitbc_cli/core/main.py`.

Use `TradingClient` from A2 for all RPC calls.

#### B8: Integration Tests

`apps/trading/tests/test_v080_inter_chain.py` — tests for:
- InterChainTrade + IslandRegistry model creation
- Chain discovery (register, list, health)
- Inter-chain trade lifecycle (create → list → get → status → history)
- Matching engine (price-time priority, cross-chain matching)
- CLI commands (smoke tests)

---

## Coordination

### Shared Files

No shared files are touched by both agents. Agent A owns `aitbc/trading/` (new package). Agent B owns `apps/trading/`, `cli/`. Agent B consumes Agent A's `TradingClient`, trading types, and bridge integration utilities.

### Sequencing

1. **Phase 1** (parallel): Agent A starts A1-A3 (shared SDK), Agent B starts B1 (config) + B2 (domain models)
2. **Phase 2** (Agent A first): Agent A completes A4 (tests), Agent B starts B3-B5 (blockchain/bridge client, chain discovery, trade lifecycle — depends on A1 types + A3 bridge utilities)
3. **Phase 3** (Agent B): B6 (matching engine), B7 (CLI — needs A2 client), B8 (tests)

### Dependencies

```
v0.7.0-v0.7.2 (bridge RPC endpoints) ✅
    │
    ├── A1 (types) ──┐
    ├── A2 (client) ─┤
    ├── A3 (bridge) ─┤
    │                  ├── A4 (tests)
    │                  │
    ├── B1 (config) ──┐│
    ├── B2 (models) ─┤│
    │                  │├── B3 (blockchain/bridge client)
    │                  │├── B4 (chain discovery)
    │                  │├── B5 (trade lifecycle)
    │                  │├── B6 (matching engine)
    │                  │├── B7 (CLI — needs A2)
    │                  │└── B8 (tests)
```

### Deferred to v0.8.1 / v0.9.0

- **Cross-chain offer synchronization** (v0.8.1): Distributed offer discovery, offer sync across chains, staleness detection, conflict resolution
- **Atomic cross-chain settlement** (v0.9.0): HTLC-based escrow locking, atomic release, timeout/refund, chaos testing
- **Dispute resolution framework**: Needs design first — who can dispute, what evidence, timeout, admin arbitration path
- **Exchange app migration**: `apps/exchange/cross_chain_exchange.py` is SQLite-only with mock operations — will be deprecated or migrated in a future release
- **Coordinator-API inter-chain trading**: `apps/coordinator-api/src/app/contexts/trading/` is P2P same-chain — inter-chain extension deferred
