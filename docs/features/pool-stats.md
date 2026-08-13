# Pool Stats

Get pool statistics

- **Status**: ✅
- **Release**: v0.6.7

## Implementation Details

- `aitbc/network/http_pool.py` — import asyncio from typing import Any import httpx from aitbc.aitbc_logging import get_logger logger...
- API endpoint `GET /security-stats` implemented in `apps/coordinator-api/src/coordinator_api/contexts/security/routers/security_router.py`
- API endpoint `GET /bounties/stats` implemented in `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/bounties.py`
- API endpoint `GET /staking-stats` implemented in `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/staking.py`
- API endpoint `GET /v1/exchange/market-stats` implemented in `apps/trading/src/trading_service/routers/exchange_compat.py`
- `Blockchain Node` exposes `GET /rpc/ai/stats` (operation `ai_stats_rpc_ai_stats_get`) — AI service statistics
- `Coordinator API` exposes `GET /v1/marketplace/stats` (operation `get_marketplace_stats_v1_marketplace_stats_get`) — Get marketplace summary statistics
- `Coordinator API` exposes `GET /v1/bounty/stats` (operation `get_stats_v1_bounty_stats_get`) — Get bounty statistics

## Examples

- `GET /security-stats` (`get_security_statistics` in `apps/coordinator-api/src/coordinator_api/contexts/security/routers/security_router.py`)
- `GET /bounties/stats` (`get_bounty_statistics` in `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/bounties.py`)
- `GET /staking-stats` (`get_staking_statistics` in `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/staking.py`)
- `GET /v1/exchange/market-stats` (`get_market_stats` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /agents/{agent_wallet}/staking-pool` (`get_staking_pool` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /rpc/ai/stats` (`ai_stats_rpc_ai_stats_get`) on `Blockchain Node`
- `GET /v1/marketplace/stats` (`get_marketplace_stats_v1_marketplace_stats_get`) on `Coordinator API`
- `GET /v1/bounty/stats` (`get_stats_v1_bounty_stats_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.7`
- Manages pool configuration, worker tracking, and payout scheduling.
