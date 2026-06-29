## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.8.2 Suggestions

## Status
**PLANNED 2026-06-29** — v0.8.2 created to track items deferred from v0.8.1. NOT on the critical path (v0.9.0 does not depend on v0.8.2). All infrastructure verified as existing and reusable.

## Origin

v0.8.1 was rescoped to polling-based sync only. The following items were deferred to "v0.8.2+":
- Subscription-based sync (WebSocket)
- Real-time offer notifications
- External search index (Elasticsearch/Meilisearch)
- Gossip-based offer propagation

This release tracks those deferred items.

## Reusable Infrastructure (verified — exists and can be reused)

1. **WebSocket infrastructure** (`apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`, 136 lines)
   - Lease-based authentication pattern (lines 42-136)
   - Heartbeat/ping-pong every 20s (lines 103-112)
   - Active subscriber tracking (`_active_subscribers` dict, line 15)
   - `_stream_topic()` helper for gossip-based streaming (lines 18-27)
   - **Reuse**: Extend with `/rpc/offers/subscribe` endpoint following same pattern

2. **Gossip broker** (`apps/blockchain-node/src/aitbc_chain/gossip/broker.py`, 511 lines)
   - `InMemoryGossipBackend` (lines 99-147): asyncio.Queue-based pub/sub
   - `BroadcastGossipBackend` (lines 149-262): Redis pub/sub for cross-process
   - `GossipBroker` (lines 264-402): deduplication + priority queue wrapper
   - Topics: any string (dynamic), existing: `"blocks"`, `"transactions"`, `"blocks.{chain_id}"`
   - **Reuse**: Add `offers.{chain_id}` topic for offer change events

3. **SubscriptionClient** (`apps/blockchain-node/src/aitbc_chain/subscription_client.py`, 405 lines)
   - Three transports: websocket, http, redis (line 27)
   - Auto-reconnect on `ConnectionClosed` with 5s delay (lines 262-268)
   - Fallback to pull mode on error (line 267, 275)
   - Lease management with heartbeat (lines 105-129, 164-216)
   - **Reuse**: Follow same reconnection and lease pattern for offer subscription client

4. **RedisCache** (`aitbc/caching/redis_cache.py`, 72 lines)
   - get/set/delete with TTL, in-memory fallback
   - **Reuse**: Already used by OfferCache (v0.8.1)

5. **OfferCache** (`aitbc/trading/offer_cache.py`, 221 lines, v0.8.1)
   - get/set/delete offers, list by chain/type, staleness tracking
   - **Reuse**: Extend with real-time update methods (invalidate on event)

6. **OfferSyncClient** (`aitbc/trading/offer_client.py`, 150 lines, v0.8.1)
   - Async HTTP client for offer sync endpoints
   - **Reuse**: Extend with WebSocket subscription methods

7. **BlockchainCache invalidation pattern** (`aitbc/caching/blockchain_cache.py`, 224 lines)
   - `subscribe_to_invalidation()` (lines 189-191)
   - `_notify_subscribers()` (lines 193-199)
   - **Reuse**: Follow same pattern for OfferCache invalidation on gossip events

## Confirmed Gaps (verified in /opt/aitbc 2026-06-29)

1. **No offer event system**: No `offer_event`, `offer_notification`, `offer_change` code anywhere. Offer changes are not published to gossip topics.
2. **No offer WebSocket endpoint**: `/rpc/offers/subscribe` does not exist. Only `/rpc/blocks`, `/rpc/transactions`, `/rpc/subscribe/ws` exist.
3. **No offer gossip topic**: `offers.{chain_id}` topic is not used anywhere. Only `blocks.*` and `transactions.*` topics exist.
4. **No external search index**: No Elasticsearch, Meilisearch, or custom search index. Only in-memory indexes in agent-coordinator (for agent discovery, not offers).
5. **No real-time notification system**: No saved query subscriptions, no debounced batch notifications, no WebSocket-based offer stream.

## Recommendations

- **Build on existing WebSocket pattern**: The `/rpc/subscribe/ws` endpoint (websocket.py:42-136) provides a proven lease-based subscription pattern. Follow it for `/v1/trading/offers/subscribe`.
- **Use existing gossip broker**: `BroadcastGossipBackend` (Redis pub/sub) is already used for block/transaction propagation. Add `offers.{chain_id}` topic for offer changes.
- **Follow SubscriptionClient reconnection pattern**: The 5s reconnect delay, pull-mode fallback, and lease management (subscription_client.py) are proven patterns. Reuse for offer subscription.
- **Defer Elasticsearch, prefer Meilisearch**: Meilisearch is lighter weight (single binary), has sub-millisecond latency, and is simpler to deploy. Elasticsearch adds operational complexity. Make search index optional with in-memory fallback.
- **Debounced notifications**: Collect offer changes for 1s (configurable) before sending batch notification. Avoids flooding when many offers change simultaneously.
- **Polling remains as fallback**: v0.8.1 polling-based sync should remain as fallback when subscription fails. This ensures robustness.
- **NOT on critical path**: v0.9.0 (atomic settlement) does not depend on v0.8.2. v0.8.2 can ship after v0.9.0 or in parallel. Do not delay v0.9.0 for v0.8.2.
- **Search index is optional**: The in-memory search from v0.8.1 is sufficient for most use cases. External search index is only needed at scale (1000+ offers across many chains). Make it opt-in.
