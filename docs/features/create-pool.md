# Create Pool

Create a new mining pool

- **Status**: ✅
- **Release**: v0.6.7

## Implementation Details

- `aitbc/network/http_pool.py` — import asyncio from typing import Any import httpx from aitbc.aitbc_logging import get_logger logger...
- `apps/blockchain-node/create_enhanced_genesis.py` — Enhanced script to create genesis block with new features
- `apps/blockchain-node/scripts/create_genesis_wallet.py` — Create genesis wallet with secure random secp256k1 private key
- `apps/blockchain-node/create_genesis.py` — Simple script to create genesis block
- `apps/blockchain-node/scripts/create_bootstrap_genesis.py` — Generate a genesis file with initial distribution for the exchange economy.
- `Blockchain Node` exposes `POST /rpc/register-account` (operation `create_account_route_rpc_register_account_post`) — Report the on-chain state of an account address
- `Coordinator API` exposes `POST /v1/bounty/create` (operation `create_bounty_v1_bounty_create_post`) — Create a new bounty
- `Coordinator API` exposes `POST /v1/governance-enhanced/staking/pools` (operation `create_staking_pool_v1_governance_enhanced_staking_pools_post`) — Create Staking Pool

## Examples

- `POST /staking/pools` (`create_staking_pool` in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/governance_enhanced.py`)
- `GET /health` (`health` in `apps/trading/src/trading_service/routers/system.py`)
- `GET /ready` (`ready` in `apps/trading/src/trading_service/routers/system.py`)
- `GET /live` (`live` in `apps/trading/src/trading_service/routers/system.py`)
- `GET /v1/trading/status` (`trading_status` in `apps/trading/src/trading_service/routers/system.py`)
- `POST /rpc/register-account` (`create_account_route_rpc_register_account_post`) on `Blockchain Node`
- `POST /v1/bounty/create` (`create_bounty_v1_bounty_create_post`) on `Coordinator API`
- `POST /v1/governance-enhanced/staking/pools` (`create_staking_pool_v1_governance_enhanced_staking_pools_post`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.7`
- Manages pool configuration, worker tracking, and payout scheduling.
- The pool-hub manages miner registration, job assignment, scoring, and reward distribution.
