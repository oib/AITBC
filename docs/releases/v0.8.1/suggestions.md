## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.8.1 Suggestions

## Status
**RE-VERIFIED 2026-06-29** — All 5 original claims CONFIRMED. Prerequisite status corrected (v0.8.0 is not "Concept Plan" — trading service exists, Agent A complete).

## Stale Claims Corrected

| Original Claim | Actual Status (2026-06-29) |
|----------------|---------------------------|
| "v0.8.0 is a Concept Plan (no trading service exists yet)" | **FALSE** — `apps/trading/` exists (1011 lines), v0.8.0 Agent A complete (`939bb066f`) |
| "IslandManager has 14 methods" | **MINOR ERROR** — has 20 methods (including private), but core claim is correct: zero offer sync |
| "New offer sync daemon (`aitbc-offer-sync` service)" | **CORRECTED** — offer sync runs as part of existing trading service, not a separate daemon |

## Confirmed Gaps (verified in /opt/aitbc 2026-06-29)

1. **IslandManager has no offer sync**: 20 methods, all membership/bridge/peer management. Zero offer sync capability. (`island_manager.py:58-269`)
2. **No distributed search index**: No Elasticsearch, Meilisearch, or custom search index in codebase. Only documentation references.
3. **No staleness config**: No `OFFER_STALENESS_THRESHOLD` or similar config in codebase. Only in documentation.
4. **No dedicated offer query RPC**: Only generic `/rpc/transactions` with `transaction_type` filter and `/rpc/gpus` with `chain_id` filter. No dedicated offer sync RPC.
5. **No offer sync code**: No `offer_sync`, `offer_discovery`, `sync_offers`, `discover_offers` code exists for cross-chain sync. (coordinator-api has `sync_offers` but it's for local miner registration, not cross-chain.)

## Reusable Infrastructure (verified — exists and can be reused)

1. **MarketplaceOffer model** (`packages/aitbc-shared/aitbc_shared/models/marketplace.py`) — chain-aware (chain_id field, v0.6.6), with provider, capacity, price, gpu_model, region, status
2. **OfferFSM** (`aitbc/marketplace/offer_fsm.py`) — 5 states (AVAILABLE, RESERVED, IN_USE, DELISTED, EXPIRED) with validated transitions
3. **BlockchainRPCClient** (`aitbc/marketplace/blockchain_rpc.py`) — chain-aware, `query_offers(chain_id, status, gpu_model, region, limit)`
4. **GPU resource RPC** (`apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py`) — `GET /rpc/gpus` with chain_id filter, `GET /rpc/gpu/info/{gpu_id}`
5. **Transaction query RPC** (`apps/blockchain-node/src/aitbc_chain/rpc/transactions.py:172-249`) — `GET /rpc/transactions` with `transaction_type` + `chain_id` filters
6. **RedisCache** (`aitbc/caching/redis_cache.py`) — get/set/delete with TTL, in-memory fallback
7. **Gossip broker** (`apps/blockchain-node/src/aitbc_chain/gossip/broker.py`) — InMemory + Redis pub/sub (for future subscription-based sync)
8. **WebSocket endpoints** (`apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`) — /rpc/blocks, /rpc/transactions (for future subscription-based sync)
9. **v0.8.0 trading SDK** (`aitbc/trading/`) — types, TradingClient, TradingBridgeClient (extendable with offer sync)

## Recommendations

- **Start with polling-based sync only**: Subscription-based sync (WebSocket) adds complexity (auth, reconnection, backpressure). Polling works with existing RPC endpoints. Defer subscriptions to v0.8.2+.
- **Reuse existing offer infrastructure**: MarketplaceOffer model, OfferFSM, BlockchainRPCClient, GPU resource RPC, transaction query RPC all exist and are chain-aware. Do NOT reimplement.
- **Use RedisCache for offer cache**: RedisCache already exists with TTL + in-memory fallback. Create OfferCache wrapper with offer-specific staleness tracking.
- **Make staleness configurable per chain**: Default 5 min for fast chains, 30 min for slow chains. Store as dict in config: `{"ait-hub": 300, "ait-island1": 1800}`.
- **Offer sync runs in trading service**: NOT a separate daemon. The trading service (`apps/trading/`) already has FastAPI, service layer, and systemd service. Add OfferSyncService as a background task within the trading service.
- **Source-chain-wins conflict resolution**: When the same offer appears on multiple chains, the source chain is authoritative. Use last-write-wins with timestamp as tiebreaker.
- **Do NOT use external search index**: Elasticsearch/Meilisearch adds operational complexity. Local Redis cache + in-memory search is sufficient for v0.8.1. Defer external index to future release.
- **Do NOT modify blockchain-node**: Offer sync is an off-chain service layer. Use existing RPC endpoints (GET /rpc/gpus, GET /rpc/transactions). No new blockchain-node endpoints needed in v0.8.1.
- **GPU_MARKETPLACE is the offer transaction type**: Confirmed in `gas.py:21` and `marketplace.py:63`. Offers are stored as GPU_MARKETPLACE transactions with JSON payload. No MARKETPLACE_OFFER type exists in the blockchain.
