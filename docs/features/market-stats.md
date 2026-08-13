# Market Stats

Get market statistics

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/services/market_analytics.py` — Market Analytics Service for real-time metrics and trend analysis.
- API endpoint `GET /v1/exchange/market-stats` implemented in `apps/trading/src/trading_service/routers/exchange_compat.py`
- API endpoint `GET /security-stats` implemented in `apps/coordinator-api/src/coordinator_api/contexts/security/routers/security_router.py`
- API endpoint `GET /marketplace/stats` implemented in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`
- `Blockchain Node` exposes `GET /rpc/ai/stats` (operation `ai_stats_rpc_ai_stats_get`) — AI service statistics
- `Coordinator API` exposes `GET /v1/marketplace/stats` (operation `get_marketplace_stats_v1_marketplace_stats_get`) — Get marketplace summary statistics
- `Coordinator API` exposes `GET /v1/bounty/stats` (operation `get_stats_v1_bounty_stats_get`) — Get bounty statistics

## Examples

- `GET /v1/exchange/market-stats` (`get_market_stats` in `apps/trading/src/trading_service/routers/exchange_compat.py`)
- `GET /security-stats` (`get_security_statistics` in `apps/coordinator-api/src/coordinator_api/contexts/security/routers/security_router.py`)
- `GET /marketplace/stats` (`get_marketplace_stats` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`)
- `GET /exchange/market-stats` (`get_market_stats` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/exchange.py`)
- `GET /bounties/stats` (`get_bounty_statistics` in `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/bounties.py`)
- `GET /rpc/ai/stats` (`ai_stats_rpc_ai_stats_get`) on `Blockchain Node`
- `GET /v1/marketplace/stats` (`get_marketplace_stats_v1_marketplace_stats_get`) on `Coordinator API`
- `GET /v1/bounty/stats` (`get_stats_v1_bounty_stats_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Provides portfolio management, order execution, market data ingestion, and risk controls.
