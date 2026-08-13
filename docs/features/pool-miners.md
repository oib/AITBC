# Pool Miners

Get miners in a pool

- **Status**: ✅
- **Release**: v0.6.7

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/services/miners.py` — Deregister a miner from the system
- `aitbc/network/http_pool.py` — import asyncio from typing import Any import httpx from aitbc.aitbc_logging import get_logger logger...
- API endpoint `GET /agents/{agent_wallet}/staking-pool` implemented in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`
- API endpoint `GET /miners` implemented in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/monitor.py`
- API endpoint `POST /miners/{miner_id}/earnings` implemented in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py`
- `Blockchain Node` exposes `GET /rpc/mining/miners` (operation `list_miners_route_rpc_mining_miners_get`) — List active miners
- `Coordinator API` exposes `GET /v1/admin/miners` (operation `list_miners_v1_admin_miners_get`) — List miners
- `Coordinator API` exposes `POST /v1/miners/{miner_id}/earnings` (operation `get_miner_earnings_v1_miners__miner_id__earnings_post`) — Get miner earnings

## Examples

- `GET /agents/{agent_wallet}/staking-pool` (`get_staking_pool` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /miners` (`get_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/monitor.py`)
- `POST /miners/{miner_id}/earnings` (`get_miner_earnings` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py`)
- `GET /staking/pools` (`get_developer_staking_pools` in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/governance_enhanced.py`)
- `GET /bridge/liquidity-pools` (`get_liquidity_pools` in `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/routers/cross_chain_integration.py`)
- `GET /rpc/mining/miners` (`list_miners_route_rpc_mining_miners_get`) on `Blockchain Node`
- `GET /v1/admin/miners` (`list_miners_v1_admin_miners_get`) on `Coordinator API`
- `POST /v1/miners/{miner_id}/earnings` (`get_miner_earnings_v1_miners__miner_id__earnings_post`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.7`
- The pool-hub manages miner registration, job assignment, scoring, and reward distribution.
