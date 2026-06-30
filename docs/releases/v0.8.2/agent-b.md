# v0.8.2 Advanced Offer Sync — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add offer event publishing, offer WebSocket endpoint, gossip integration, subscription endpoints, CLI commands, and tests.

**Working directory**: `/opt/aitbc/apps/trading/`, `/opt/aitbc/apps/blockchain-node/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A2 complete. v0.8.1 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/trading/src/trading_service/ apps/blockchain-node/src/aitbc_chain/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/trading/src:aitbc ./venv/bin/python -m pytest apps/trading/tests/test_v082_offer_subscription.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Offer event publishing — publish OfferEvent to gossip broker on offer changes | 🔴 P0 | `apps/trading/src/trading_service/services/offer_sync_service.py` (extend) | ✅ |
| B2 | Offer WebSocket endpoint — WS /v1/trading/offers/subscribe/ws for offer streaming | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B3 | Gossip integration — add `offers.{chain_id}` topic to gossip broker | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` (extend) | ✅ |
| B4 | Subscription endpoints — POST /v1/trading/offers/subscribe, POST /v1/trading/offers/heartbeat | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B5 | CLI commands — trade subscribe, unsubscribe, subscription-status | Medium | `cli/aitbc_cli/commands/trade.py` (extend) | ✅ |
| B6 | Tests — subscription, WebSocket, gossip, fallback to polling | High | `apps/trading/tests/test_v082_offer_subscription.py` (new) | ✅ |

---

## B1: Offer Event Publishing

Extend `apps/trading/src/trading_service/services/offer_sync_service.py`:
- Publish `OfferEvent` to gossip broker on offer changes
- Use `offers.{chain_id}` topic (per-chain partitioning)
- Publish on created, updated, deleted events
- Use Agent A's `OfferEvent` from A1

---

## B2: Offer WebSocket Endpoint

Add to `apps/trading/src/trading_service/main.py`:
- `WS /v1/trading/offers/subscribe/ws` — WebSocket endpoint for offer streaming
- Follow pattern from `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`
- Lease-based auth with `node_id`
- Heartbeat for lease renewal
- Filter support (service_type, min_price, max_price, region, gpu_model)

---

## B3: Gossip Integration

Extend `apps/blockchain-node/src/aitbc_chain/gossip/broker.py`:
- Add `offers.{chain_id}` topic for offer change events
- Follow existing per-chain topic pattern (`blocks.{chain_id}`, `transactions.{chain_id}`)
- Priority defaults to `PRIORITY_STATUS` (4) — no change needed to `_priority_for_topic()`

---

## B4: Subscription Endpoints

Add to `apps/trading/src/trading_service/main.py`:
- `POST /v1/trading/offers/subscribe` — register, get lease
- `POST /v1/trading/offers/heartbeat` — extend lease
- Follow pattern from `apps/blockchain-node/src/aitbc_chain/rpc/subscription.py`
- Use different lease key prefix: `lease:offer_subscriber:{node_id}`

---

## B5: CLI Commands

Extend `cli/aitbc_cli/commands/trade.py`:
- `aitbc trade subscribe` — subscribe to offer events
- `aitbc trade unsubscribe` — unsubscribe from offer events
- `aitbc trade subscription-status` — get subscription status

Use Agent A's `OfferSubscriptionClient` from A2.

---

## B6: Tests

`apps/trading/tests/test_v082_offer_subscription.py` — tests for:
- Offer event publishing
- WebSocket subscription
- Gossip integration
- Subscription endpoints
- CLI commands
- Fallback to polling

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.2 — Advanced Offer Sync
**Agent**: Agent B (Apps & Infrastructure)
