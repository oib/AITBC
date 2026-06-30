# v0.8.0 Inter-Chain Trading Basics — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

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

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (trading types, trading client, bridge integration, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (trading config, domain models, RPC clients, chain discovery, trade lifecycle, matching engine, CLI, integration tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Already Fixed / Exists](#already-fixed--exists-verified--no-work-needed)
- [Architecture](#architecture-inter-chain-trading-v080)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Trading Types](./agent-a.md#a1-trading-types)
- [Trading Client](./agent-a.md#a2-trading-client)
- [Bridge Integration Utilities](./agent-a.md#a3-bridge-integration-utilities)
- [Unit Tests](./agent-a.md#a4-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Trading Service Config](./agent-b.md#b1-trading-service-config)
- [Inter-Chain Domain Models](./agent-b.md#b2-inter-chain-domain-models)
- [Blockchain/Bridge RPC Client](./agent-b.md#b3-blockchainbridge-rpc-client)
- [Chain Discovery](./agent-b.md#b4-chain-discovery)
- [Inter-Chain Trade Lifecycle](./agent-b.md#b5-inter-chain-trade-lifecycle)
- [Basic Matching Engine](./agent-b.md#b6-basic-matching-engine)
- [CLI Trade Command Group](./agent-b.md#b7-cli-trade-command-group)
- [Integration Tests](./agent-b.md#b8-integration-tests)

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

---

## Architecture: Inter-Chain Trading (v0.8.0)

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.0 — Inter-Chain Trading Basics
