# Offer History

Get offer history

- **Status**: ✅
- **Release**: —
## Implementation Details
- `aitbc/trading/offer_types.py` — from __future__ import annotations from dataclasses import dataclass, field from enum import StrEnum...
- `aitbc/marketplace/offer_fsm.py` — from __future__ import annotations import logging from enum import StrEnum logger = logging.getLogge...
- `aitbc/trading/offer_cache.py` — Get a single offer from the cache.
- `apps/trading/src/trading_service/services/offer_search_service.py` — Initialize the external search backend client.
- `Marketplace` exposes `GET /v1/marketplace/offers/{offer_id}/history` (operation `get_offer_history_v1_marketplace_offers__offer_id__history_get`) — Get Offer History
- `Blockchain Node` exposes `GET /rpc/consensus/slashing-history` (operation `consensus_slashing_history_route_rpc_consensus_slashing_history_get`) — Get slashing history
- `Coordinator API` exposes `GET /v1/jobs/history` (operation `get_job_history_v1_jobs_history_get`) — Get job history
## Examples

- `GET /v1/trading/inter-chain/history` (`get_inter_chain_trade_history` in `apps/trading/src/trading_service/routers/inter_chain.py`)
- `GET /v1/trading/offers/sync-status` (`get_offer_sync_status` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/cache` (`get_cached_offers` in `apps/trading/src/trading_service/routers/offers.py`)
- `GET /v1/trading/offers/subscription-status` (`get_subscription_status` in `apps/trading/src/trading_service/routers/subscriptions.py`)
- `GET /offers/cross-chain` (`get_integrated_marketplace_offers` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/global_marketplace_integration.py`)
- `GET /v1/marketplace/offers/{offer_id}/history` (`get_offer_history_v1_marketplace_offers__offer_id__history_get`) on `Marketplace`
- `GET /rpc/consensus/slashing-history` (`consensus_slashing_history_route_rpc_consensus_slashing_history_get`) on `Blockchain Node`
- `GET /v1/jobs/history` (`get_job_history_v1_jobs_history_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
