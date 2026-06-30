# v0.8.0 Inter-Chain Trading Basics — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add trading service Settings class, InterChainTrade + IslandRegistry SQLModel tables, blockchain/bridge RPC client, chain discovery, inter-chain trade lifecycle endpoints, basic matching engine, CLI commands, integration tests.

**Working directory**: `/opt/aitbc/apps/trading/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A3 complete. v0.7.0-v0.7.2 complete (bridge RPC endpoints available).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/trading/src/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/trading/src:aitbc ./venv/bin/python -m pytest apps/trading/tests/test_v080_inter_chain.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add trading service Settings class (blockchain_rpc_url, bridge_rpc_url, chain_id, matching params) | 🔴 P0 | `apps/trading/src/trading_service/config.py` (new) | ✅ |
| B2 | Add InterChainTrade + IslandRegistry SQLModel tables + Alembic migration | 🔴 P0 | `apps/trading/src/trading_service/domain/inter_chain.py` (new), `apps/trading/alembic/versions/` (new) | ✅ |
| B3 | Add blockchain/bridge RPC client to trading service | 🔴 P0 | `apps/trading/src/trading_service/clients/blockchain.py` (new), `apps/trading/src/trading_service/clients/bridge.py` (new) | ✅ |
| B4 | Chain discovery — island registry sync, chain health monitoring, register/list/health endpoints | 🔴 P0 | `apps/trading/src/trading_service/services/chain_discovery.py` (new), `main.py` (extend) | ✅ |
| B5 | Inter-chain trade lifecycle — create, list, get, status, history endpoints | 🔴 P0 | `apps/trading/src/trading_service/services/inter_chain_service.py` (new), `main.py` (extend) | ✅ |
| B6 | Basic matching engine (price-time priority across chains) | High | `apps/trading/src/trading_service/services/matching_engine.py` (new) | ✅ |
| B7 | CLI trade command group | 🔴 P0 | `cli/aitbc_cli/commands/trade.py` (new), `cli/aitbc_cli/core/main.py` (extend) | ✅ |
| B8 | Integration tests | High | `apps/trading/tests/test_v080_inter_chain.py` (new) | ✅ |

---

## B1: Trading Service Config

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

---

## B2: Inter-Chain Domain Models

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

---

## B3: Blockchain/Bridge RPC Client

Create `apps/trading/src/trading_service/clients/blockchain.py`:
- `BlockchainRPCClient` — wraps blockchain node RPC for chain health, balance queries

Create `apps/trading/src/trading_service/clients/bridge.py`:
- `BridgeClient` — wraps bridge RPC for lock/confirm/status operations (use Agent A's `TradingBridgeClient` from A3)

---

## B4: Chain Discovery

Create `apps/trading/src/trading_service/services/chain_discovery.py`:
- Island registry sync loop (periodic task)
- Chain health monitoring
- Register/list/health endpoints in `main.py`

---

## B5: Inter-Chain Trade Lifecycle

Create `apps/trading/src/trading_service/services/inter_chain_service.py`:
- Create inter-chain trade
- List trades
- Get trade by ID
- Get trade status
- Trade history endpoint

Add endpoints to `main.py`:
- `POST /v1/trading/inter-chain/create`
- `GET /v1/trading/inter-chain`
- `GET /v1/trading/inter-chain/{id}`
- `GET /v1/trading/inter-chain/{id}/status`
- `GET /v1/trading/inter-chain/history`

---

## B6: Basic Matching Engine

Create `apps/trading/src/trading_service/services/matching_engine.py`:
- Price-time priority across chains
- Match trades against offers
- Return `TradeMatchResult` from Agent A's types

---

## B7: CLI Trade Command Group

Create `cli/aitbc_cli/commands/trade.py`:
- `aitbc trade create --source-chain --dest-chain --sender --recipient --amount`
- `aitbc trade list [--status]`
- `aitbc trade chains`
- `aitbc trade get --trade-id`
- `aitbc trade status --trade-id`
- `aitbc trade register-chain --chain-id --endpoint`
- `aitbc trade health --chain-id`
- `aitbc trade history [--trade-id]`

Register command group in `cli/aitbc_cli/core/main.py`.

Uses Agent A's `TradingClient` (A2) and `TradingBridgeClient` (A3).

---

## B8: Integration Tests

Create `apps/trading/tests/test_v080_inter_chain.py`:
- Test inter-chain trade lifecycle (create, list, get, status, history)
- Test chain discovery (register, list, health)
- Test matching engine (price-time priority)
- Test CLI commands (mock TradingClient)

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.0 — Inter-Chain Trading Basics
**Agent**: Agent B (Apps & Infrastructure)
