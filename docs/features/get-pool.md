# Get Pool

Get pool information

- **Status**: ✅
- **Release**: v0.6.7

## Implementation Details

- `aitbc/network/http_pool.py` — import asyncio from typing import Any import httpx from aitbc.aitbc_logging import get_logger logger...
- API endpoint `GET /agents/{agent_wallet}/staking-pool` implemented in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`
- API endpoint `GET /staking/pools` implemented in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/governance_enhanced.py`
- API endpoint `GET /bridge/liquidity-pools` implemented in `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/routers/cross_chain_integration.py`
- API endpoint `GET /mempool` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/core.py`
- `Blockchain Node` exposes `GET /rpc/info` (operation `get_info_route_rpc_info_get`) — Get blockchain information
- `Blockchain Node` exposes `GET /rpc/network-info` (operation `get_network_info_route_rpc_network_info_get`) — Get network information for joining
- `Blockchain Node` exposes `GET /rpc/account/{address}` (operation `get_account_route_rpc_account__address__get`) — Get account information

## Examples

- `GET /agents/{agent_wallet}/staking-pool` (`get_staking_pool` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /staking/pools` (`get_developer_staking_pools` in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/governance_enhanced.py`)
- `GET /bridge/liquidity-pools` (`get_liquidity_pools` in `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/routers/cross_chain_integration.py`)
- `GET /mempool` (`get_mempool_api_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/core.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/info` (`get_info_route_rpc_info_get`) on `Blockchain Node`
- `GET /rpc/network-info` (`get_network_info_route_rpc_network_info_get`) on `Blockchain Node`
- `GET /rpc/account/{address}` (`get_account_route_rpc_account__address__get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.7`
- Manages pool configuration, worker tracking, and payout scheduling.
