## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.8.0 Suggestions

## Status
**RE-VERIFIED 2026-06-29** — Original analysis had multiple stale/incorrect claims. Re-verified against current codebase state.

## Stale Claims Corrected

| Original Claim | Actual Status (2026-06-29) |
|----------------|---------------------------|
| "No trading service exists" | **FALSE** — `apps/trading/` exists with 1011 lines (FastAPI, domain models, service layer, SQLite, systemd service) |
| "v0.7.1 Bridge Security not done" | **FALSE** — Complete and committed (`a4ea61295` + `1fcf1e829`) — multi-sig, validator sets, block sigs |
| "v0.7.2 Bridge Verification not done" | **FALSE** — Complete and committed (`09fa64342` + `9a7b17a34`) — Merkle proofs, finality, oracle, release unfenced |
| "CLI breaking change: market run → trade create" | **FALSE** — `aitbc market run` does not exist. `aitbc trade` is purely additive |
| "Trade service requires PostgreSQL" | **MISLEADING** — `storage.py:14` already supports `DATABASE_URL` env var for PostgreSQL. SQLite is dev default |

## Confirmed Gaps (verified in /opt/aitbc 2026-06-29)

1. **InterChainTrade schema not defined**: No SQLModel class exists anywhere. Existing models (`apps/trading/src/trading_service/domain/trading.py` 369 lines, `apps/coordinator-api/src/app/contexts/trading/domain/trading.py` 784 lines) are P2P agent-to-agent with NO source_chain/dest_chain/chain_id fields.
2. **IslandRegistry SQLModel table not defined**: Config parsers exist (`aitbc/network/island_registry.py` 104 lines, `cli/config_data/chains.py` 122 lines) but no SQLModel table for persistent chain registry in trading service.
3. **CLI trade.py missing**: `cli/aitbc_cli/commands/trade.py` does NOT exist. `cli/aitbc_cli/commands/exchange/trading.py` (182 lines) exists but is for external exchanges (Binance, Coinbase), not inter-chain AITBC trading.
4. **No blockchain/bridge RPC client in trading service**: `apps/trading/src/` has no `AITBCHTTPClient`, `BlockchainRPCClient`, or `BridgeClient` integration. No `blockchain_rpc_url` or `bridge_rpc_url` config.
5. **No Settings class in trading service**: `apps/trading/src/trading_service/` has no `config.py`, no `Settings(BaseSettings)`, no chain_id config.
6. **No matching engine in trading service**: `apps/trading/src/trading_service/services/trading_service.py` (133 lines) has basic CRUD but no matching engine. Coordinator-API has `P2PTradingProtocol` but it's same-chain only.
7. **Exchange app is mock-based**: `apps/exchange/cross_chain_exchange.py` (457 lines) uses SQLite with mock chain operations (`asyncio.sleep()` + fake tx hashes). NOT a v0.8.0 target — will be deprecated or migrated separately.

## Recommendations

- **Freeze InterChainTrade schema first**: Define the SQLModel before building the matching engine. Fields: `trade_id`, `source_chain`, `dest_chain`, `status`, `source_tx_hash`, `dest_tx_hash`, `amount`, `sender`, `recipient`, `offer_id`, `price`, `quantity`, `created_at`, `updated_at`.
- **Extend existing trading service**: Do NOT create a new app. `apps/trading/` already has FastAPI, domain models, service layer, systemd service. Add inter-chain models, bridge client, chain discovery, matching engine to the existing service.
- **Reuse bridge RPC endpoints**: 15 bridge endpoints are available (v0.7.0-v0.7.2). Use `BridgeClient` from `aitbc.bridge` for inter-chain escrow operations. Do NOT reimplement bridge logic.
- **Defer atomic settlement to v0.9.0**: v0.8.0 only handles create → match → agree lifecycle. Escrow locking and settlement are v0.9.0 (HTLC-based).
- **Defer cross-chain offer sync to v0.8.1**: Distributed offer discovery and synchronization is a separate hard problem.
- **Defer dispute resolution**: Needs design first — who can dispute, what evidence, timeout, admin arbitration path. Not a v0.8.0 target.
- **Do NOT migrate exchange app**: `apps/exchange/cross_chain_exchange.py` is SQLite-only with mocks. It will be deprecated or migrated in a future release. v0.8.0 extends `apps/trading/` instead.
- **Port 8202 is correct**: Blockchain node RPC and bridge are both on port 8202 (NOT 8006 which is stale legacy).
