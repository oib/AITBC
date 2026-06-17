# AITBC v0.4.14 Release Notes

**Date**: June 8, 2026
**Status**: ✅ Released
**Scope**: Infrastructure Activation, Security & Performance, Monitoring
**Priority**: High
**Chain**: ait-hub.aitbc.bubuit.net

## 🎯 Overview

AITBC v0.4.14 activates and fully integrates the infrastructure features planned in v0.4.9–v0.4.13 into the live production hub. This release includes: PostgreSQL-backed governance service deployment, Redis caching on blockchain account endpoints with proper cache invalidation, input security validation on marketplace operations, Prometheus/Grafana monitoring stack with 8/8 targets, exchange service activation, a critical VPS resource stability fix that eliminates process spawn storms, and full WebSocket push sync for follower nodes with automatic pull fallback.

## 📊 Implementation Status

### ✅ Phase 1: Critical Infrastructure

**1.1 Redis Caching (v0.4.10 activation)**
- ✅ Verified Redis running on `localhost:6379` (database 0 for blockchain-node, 1 for governance, 2 for exchange)
- ✅ Added `REDIS_URL=redis://localhost:6379/0` to `/etc/aitbc/blockchain.env`
- ✅ Integrated `RedisCache` into `apps/blockchain-node/src/aitbc_chain/rpc/accounts.py`
  - `get_account` and `get_account_details` now cache responses with 30s TTL
  - Cache keys: `account_balance:{chain_id}:{address}` and `account_details:{chain_id}:{address}`
- ✅ Added Redis cache invalidation to `apps/blockchain-node/src/aitbc_chain/state/state_transition.py`
  - `apply_transaction()` now deletes cache entries for sender and recipient after every confirmed balance change

**1.2 PostgreSQL for Governance Service (v0.4.12 activation)**
- ✅ Created PostgreSQL database `aitbc_governance` and user `aitbc_governance`
- ✅ Updated `apps/governance/alembic.ini` to use `postgresql+psycopg2://` connection string
- ✅ Ran Alembic initial migration (`001_initial_governance_schema.py`) — schema created successfully
- ✅ Fixed `apps/governance/src/governance_service/storage.py`:
  - Refactored engine creation to be lazy (`_create_engine()`) so env vars are read at runtime not import time
  - `init_db()` now skips `create_all` when `DB_TYPE=postgresql` (Alembic owns schema, avoids `IntegrityError` on ENUM recreation)
- ✅ Updated `apps/governance/aitbc-governance.service` with PostgreSQL env vars (`DB_TYPE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`) and `REDIS_URL`
- ✅ Installed `psycopg2-binary` and `asyncpg` drivers

### ✅ Phase 4: External Blockchain Exchange (v0.4.9 activation)

**4.1 Bridge Contract Deployment (Sepolia)**
- ✅ Deployed `CrossChainBridge.sol` to Ethereum Sepolia testnet
  - Contract address: `0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA`
  - Deployer wallet: `0x818018F30d8F5FB7AE7a64f25895F15110923748` (0.05 ETH funded via Google faucet)
  - Infura RPC configured (`ETH_RPC_URL=https://sepolia.infura.io/v3/...`)
  - Hardhat config updated with Sepolia network
  - Deployment recorded in `/opt/aitbc/contracts/deployments-bridge-sepolia.json`
- ✅ Exchange service updated to read `BRIDGE_CONTRACT_ADDRESS` from environment
  - `GET /v1/bridge/status` now returns `status: deployed` with contract address

**4.2 Oracle Integration (Chainlink + CoinGecko)**
- ✅ Created `@/opt/aitbc/aitbc/oracles/price_oracle.py`
  - `ChainlinkOracle` — reads ETH/USD, BTC/USD, LINK/USD from on-chain aggregators (active when `ETH_RPC_URL` set)
  - `CoinGeckoOracle` — public REST fallback, 60s cache, no API key required
  - `PriceOracle` — composite with auto-fallback (Chainlink → CoinGecko)
  - Global singleton `get_price_oracle()`
- ✅ Live prices confirmed: ETH=$1,669, BTC=$63,394, LINK=$7.90 (source: CoinGecko)
- ✅ Exchange API endpoint: `GET /v1/bridge/price?base=ETH&quote=USD` returns oracle data

**4.3/4.4 Exchange Bridge API + CLI Commands**
- ✅ Exchange API endpoints (port 8106):
  - `GET /v1/bridge/price` — oracle price feed
  - `GET /v1/bridge/status` — bridge configuration status
  - `GET /v1/bridge/deposits` — list bridge deposits with status filter, pagination
  - `GET /v1/bridge/deposit/{tx_hash}` — get single deposit details
  - `POST /v1/bridge/estimate` — estimate AIT amount for given ETH amount
  - `POST /v1/bridge/deposit` — ETH→AIT deposit (stub, returns estimate)
  - `POST /v1/bridge/withdraw` — AIT→ETH withdrawal (stub, returns estimate)
- ✅ CLI commands added to `@/opt/aitbc/cli/aitbc_cli/commands/exchange.py`:
  - `aitbc exchange price ETH USD` — get oracle price
  - `aitbc exchange bridge-deposits` — list bridge deposits
  - `aitbc exchange bridge-estimate --eth-amount 0.01` — estimate AIT for ETH
  - `aitbc exchange bridge-status` — check bridge status
  - `aitbc exchange deposit --amount 0.1 --ait-address ... --dry-run` — deposit estimate
  - `aitbc exchange withdraw --amount 100 --eth-address ... --dry-run` — withdrawal estimate
  - `aitbc exchange swap --from-token ETH --to-token BTC --amount 1.5` — swap estimate

### ✅ Phase 2: Security & Performance (v0.4.10)

**2.1 Secret Management Rotation Scheduler**
- ✅ Added `start_rotation_scheduler()` method to `SecretManager` in `aitbc/crypto/security.py`
  - Runs as a daemon thread checking for expired secrets every N hours
  - Calls `cleanup_expired_secrets()` and logs audit event on each cleanup run
- ✅ Added `get_secret_manager()` global singleton factory with auto-start of rotation scheduler
  - Reads `AITBC_SECRET_MANAGER_KEY` from environment for encryption key

**2.2 Blockchain Input Validation (v0.4.10 activation)**
- ✅ Integrated `SecurityValidator` and `log_security_event` from `aitbc/security_hardening.py` into `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py`
  - `marketplace_create` validates price via `SecurityValidator.validate_amount()` — rejects negative values with HTTP 400
  - Description sanitized via `SecurityValidator.sanitize_html()` — XSS tags HTML-escaped before storage
  - Security audit event logged (`marketplace_listing_created`, `marketplace_create_invalid_amount`)
- ✅ Fixed marketplace router registration:
  - `marketplace.py` now defines its own `APIRouter` (avoiding circular import with `router.py`)
  - Router included in `apps/blockchain-node/src/aitbc_chain/app.py` under `/rpc` prefix
  - New endpoints: `GET /rpc/marketplace/listings`, `POST /rpc/marketplace/create`, `GET /rpc/marketplace/listing/{id}`

### ✅ Phase 3: Governance Service Deployment (v0.4.12)

- ✅ Governance service running on `http://127.0.0.1:8105` with 1 uvicorn worker
- ✅ Systemd service `aitbc-governance.service` installed, enabled, and starting successfully
- ✅ Health check: `GET /health` → `{"status":"healthy","service":"governance-service"}`
- ✅ Status check: `GET /v1/governance/status` → `{"status":"operational"}`
- ✅ Added Prometheus metrics endpoint: `GET /metrics`
- ✅ PostgreSQL session pool: `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`

### ✅ Phase 4: Exchange Service Activation (v0.4.9)

- ✅ `apps/exchange/aitbc-exchange.service` installed and enabled at boot
- ✅ Fixed `PYTHONPATH` to include `/opt/aitbc` for `aitbc` module resolution
- ✅ Added env vars: `REDIS_URL=redis://localhost:6379/2`, `BLOCKCHAIN_RPC_URL=http://localhost:8202`
- ✅ Exchange API running on `http://127.0.0.1:8106`
- ✅ Health check: `GET /api/health` → `{"status":"ok"}`
- ✅ Added Prometheus metrics endpoint: `GET /metrics` to `ExchangeAPIHandler`

### ✅ Phase 6: ETH-to-AIT Bridge Implementation

**Bridge Monitor Service**
- ✅ Created `apps/bridge-monitor/src/bridge_monitor/main.py` — polling service for Sepolia deposits
  - Polls Ethereum Sepolia every 30s for ETH deposits to `0x818018F30d8F5FB7AE7a64f25895F15110923748`
  - Parses AIT recipient address from transaction `input` data field
  - Calculates AIT amount using oracle prices (ETH/USD from CoinGecko, AIT/USD fixed fallback)
  - Submits AIT transfer via blockchain RPC with nonce resolution
- ✅ Created `apps/bridge-monitor/src/bridge_monitor/storage.py` — SQLite deposit tracking
  - Database: `/var/lib/aitbc/bridge_deposits.db`
  - Tracks deposit status: `pending` → `processing` → `completed`/`failed`
- ✅ Created `apps/bridge-monitor/aitbc-bridge-monitor.service` — systemd service
  - User: `aitbc-internal`, Group: `aitbc-services`
  - Auto-restart on failure
- ✅ Bridge monitor running and actively polling

**Environment Variables**
- `BRIDGE_ETH_ADDRESS=0x818018F30d8F5FB7AE7a64f25895F15110923748`
- `GENESIS_WALLET_ADDRESS=ait1db5247d03ca2e40f3995a583b2c097ab703efd4d`
- `GENESIS_WALLET_PRIVATE_KEY` (secret)
- `MIN_ETH_DEPOSIT=0.001`
- `BRIDGE_POLL_INTERVAL=30`
- `AIT_USD_FIXED_PRICE=0.01`

**Oracle Integration**
- ✅ Fixed `aitbc/oracles/price_oracle.py` to support AIT/USD fixed price fallback
  - When AIT/USD not available from Chainlink/CoinGecko, uses `AIT_USD_FIXED_PRICE` env var
  - Required for bridge AIT amount calculation (ETH/USD ÷ AIT/USD)

**nginx Configuration**
- ✅ Added proxy location `/v1/bridge/` → `http://127.0.0.1:8106/v1/bridge/`
- ✅ Added proxy location `/v1/exchange/history` → `http://127.0.0.1:8106/v1/exchange/history`
- ✅ Added proxy location `/exchange/price.json` → `http://127.0.0.1:8106/exchange/price.json`

**Exchange UI Updates**
- ✅ Updated `website/exchange.html`:
  - Added ETH-to-AIT Bridge card with deposit address, instructions, rate
  - Added copy-to-clipboard button for deposit address
  - Updated Bridge Status card with correct endpoint and display
  - Updated "Get Free AIT" section to mention bridge as alternative
  - Fixed `updatePrices()` with null checks and 6-decimal AIT price precision
  - Fixed timestamp display (multiply by 1000 for JavaScript Date)

### ✅ Phase 5: Advanced Monitoring (v0.4.13 activation)

**Prometheus Stack**
- ✅ Installed `prometheus` (v2.53.3) and `prometheus-node-exporter`
- ✅ Installed `prometheus-redis-exporter` (v1.69.0) — scrapes `localhost:6379`
- ✅ Installed `prometheus-postgres-exporter` (v0.17.1) — configured with `aitbc_governance` credentials
- ✅ Replaced default `/etc/prometheus/prometheus.yml` with AITBC hub production config:
  - `cluster: aitbc-hub`, `environment: production`, `chain: ait-hub`
  - 8 scrape jobs: prometheus, node, coordinator-api, blockchain-node, governance-service, exchange-api, redis, postgres
- ✅ Created `/etc/prometheus/rules/aitbc_alerts.yml` with 9 alert rules across 3 groups:
  - `aitbc_service_health`: ServiceDown, HighCPUUsage (>85%), HighMemoryUsage (>90%), DiskSpaceLow (<10%)
  - `aitbc_blockchain`: BlockchainNodeDown, CoordinatorAPIDown, GovernanceServiceDown, ExchangeAPIDown
  - `aitbc_redis`: RedisDown
- ✅ All 8/8 Prometheus targets UP and scraping successfully
- ✅ Prometheus accessible at `http://localhost:9090`

**Blockchain RPC Service**
- ✅ `aitbc-blockchain-rpc.service` started (was inactive) — uvicorn on `127.0.0.1:8202`
- ✅ `/metrics` endpoint already implemented via `prometheus_client.generate_latest()`

### ✅ Phase 5b: Critical VPS Resource Fix

**Problem**: High load from uvicorn worker spawn storms on a 2-core/3.7GB VPS with no swap.

**Root Cause**: 3 services configured `--workers 4` + 1 service `--workers 2` = 14 Python processes competing simultaneously for 2 CPU cores and 3.7GB RAM.

**Fix — reduced workers to 1 in all services**:
- `apps/blockchain-node/aitbc-blockchain-rpc-wrapper.py`: 4 → 1 worker, concurrency 500 → 100, backlog 1024 → 256
- `apps/coordinator-api/aitbc-coordinator-api-wrapper.py`: 4 → 1 worker, concurrency 500 → 100, backlog 1024 → 256
- `apps/api-gateway/aitbc-api-gateway.service`: 4 → 1 worker, concurrency 1000 → 100, backlog 2048 → 256
- `apps/governance/aitbc-governance.service`: 2 → 1 worker

**Result**: 8 services running, ~2.4GB RAM used, 1.2GB free — stable headroom.

## 🔧 Files Changed

| File | Change |
|------|--------|
| `aitbc/crypto/security.py` | Added `start_rotation_scheduler()`, `get_secret_manager()` singleton |
| `apps/blockchain-node/src/aitbc_chain/rpc/accounts.py` | Redis caching on `get_account`, `get_account_details` |
| `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py` | Own `APIRouter`, `SecurityValidator` integration, XSS sanitization |
| `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | Removed stale marketplace circular import |
| `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` | Cache invalidation after `apply_transaction()` |
| `apps/blockchain-node/src/aitbc_chain/app.py` | Include `marketplace_router` under `/rpc` |
| `apps/blockchain-node/aitbc-blockchain-rpc-wrapper.py` | Workers 4 → 1, limits reduced |
| `apps/coordinator-api/aitbc-coordinator-api-wrapper.py` | Workers 4 → 1, limits reduced |
| `apps/api-gateway/aitbc-api-gateway.service` | Workers 4 → 1, limits reduced |
| `apps/governance/aitbc-governance.service` | PostgreSQL/Redis env vars, workers 2 → 1 |
| `apps/governance/alembic.ini` | SQLite → PostgreSQL connection string |
| `apps/governance/src/governance_service/storage.py` | Lazy engine creation, skip `create_all` for PostgreSQL |
| `apps/governance/src/governance_service/main.py` | Added `GET /metrics` Prometheus endpoint |
| `apps/exchange/aitbc-exchange.service` | Fixed PYTHONPATH, added REDIS_URL/BLOCKCHAIN_RPC_URL |
| `apps/exchange/simple_exchange_api.py` | Added `GET /metrics`, bridge endpoints (`/v1/bridge/*`), `/v1/exchange/history` |
| `apps/bridge-monitor/src/bridge_monitor/main.py` | New — ETH deposit polling, AIT transfer submission |
| `apps/bridge-monitor/src/bridge_monitor/storage.py` | New — SQLite deposit tracking schema |
| `apps/bridge-monitor/aitbc-bridge-monitor.service` | New — systemd service definition |
| `aitbc/oracles/price_oracle.py` | Added `AIT_USD_FIXED_PRICE` env fallback |
| `/etc/nginx/sites-enabled/aitbc` | Added `/v1/bridge/`, `/v1/exchange/history`, `/exchange/price.json` proxy locations |
| `website/exchange.html` | Added bridge card, copy button, fixed price display |
| `/etc/aitbc/blockchain.env` | Added `REDIS_URL=redis://localhost:6379/0` |
| `/etc/prometheus/prometheus.yml` | Full AITBC hub production scrape config |
| `/etc/prometheus/rules/aitbc_alerts.yml` | New — 9 alert rules for hub services |
| `/etc/default/prometheus-postgres-exporter` | Configured with `aitbc_governance` credentials |
| `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py` | New — WebSocket server endpoint `/rpc/subscribe/ws` |
| `apps/blockchain-node/src/aitbc_chain/subscription_client.py` | WebSocket client, adaptive pull/push, message filtering |
| `apps/blockchain-node/src/aitbc_chain/main.py` | Adaptive sync — pass `subscription_client` to periodic task |
| `apps/blockchain-node/src/aitbc_chain/config.py` | `supported_chains` default `""`, remove hardcoded mempool credentials |
| `apps/blockchain-node/src/aitbc_chain/sync.py` | Normalize block hashes missing `0x` prefix |
| `cli/aitbc_cli/commands/market.py` | Fix double `/rpc` bug in cancel fallback |
| `/etc/aitbc/blockchain.env` | Add `MEMPOOL_DB_URL`, fix hub URLs to HTTPS, fix `default_peer_rpc_url` |
| `/etc/nginx/sites-enabled/aitbc` (hub) | WebSocket proxy `/rpc/subscribe/ws` → `http://127.0.0.1:8202` |

## 🗄️ System Status

### Services Running
```
aitbc-agent-daemon.service      active running
aitbc-blockchain-node.service   active running
aitbc-blockchain-rpc.service    active running  ← activated this release
aitbc-bridge-monitor.service    active running  ← activated this release
aitbc-coordinator-api.service   active running
aitbc-exchange.service          active running  ← activated this release
aitbc-governance.service        active running  ← activated this release
aitbc-hermes.service            active running
aitbc-wallet-daemon.service     active running
```

### Prometheus Monitoring Targets (8/8 UP)
| Job | Target | Status |
|-----|--------|--------|
| prometheus | localhost:9090 | ✅ up |
| node | localhost:9100 | ✅ up |
| coordinator-api | localhost:8203 | ✅ up |
| blockchain-node | localhost:8202 | ✅ up |
| governance-service | localhost:8105 | ✅ up |
| exchange-api | localhost:8106 | ✅ up |
| redis | localhost:9121 | ✅ up |
| postgres | localhost:9187 | ✅ up |

## 🔐 Security Summary

### Input Validation
- Negative/invalid amounts on marketplace listings → HTTP 400 rejected
- HTML/script tags in descriptions → HTML-escaped before storage
- All security events audit-logged via `log_security_event()`

### Secret Management
- `SecretManager` now auto-starts a background rotation scheduler
- Expired secrets cleaned up every hour with audit log entry
- Global `get_secret_manager()` singleton reads `AITBC_SECRET_MANAGER_KEY` from env

### Cache Security
- Account balance cache TTL: 30 seconds
- Cache invalidated immediately on any confirmed balance-changing transaction
- Separate Redis databases per service (db 0/1/2) for isolation

## 🧪 Integration Tests Results

| Test | Result |
|------|--------|
| Redis cache set/get/delete | ✅ PASS |
| Governance `/health` | ✅ HTTP 200 |
| Governance `/v1/governance/proposals` | ✅ HTTP 200 |
| Blockchain RPC `/health` | ✅ HTTP 200 |
| Exchange `/api/health` | ✅ HTTP 200 |
| Account cache (DB vs cached latency) | ✅ 61ms → 39ms |
| Marketplace invalid price validation | ✅ HTTP 400 rejected |
| Marketplace XSS sanitization | ✅ HTML-escaped |
| Prometheus 8/8 targets | ✅ all UP |
| Alert rules validation (`promtool`) | ✅ 9 rules valid |

## 🔄 Upgrade Path

### From v0.4.13 to v0.4.14

**Prerequisites**
```bash
# Install required packages
apt-get install -y prometheus prometheus-node-exporter \
  prometheus-redis-exporter prometheus-postgres-exporter

# Install Python drivers (if not present)
/opt/aitbc/venv/bin/pip install psycopg2-binary asyncpg
```

**PostgreSQL Setup**
```sql
CREATE USER aitbc_governance WITH PASSWORD 'aitbc_governance_pass';
CREATE DATABASE aitbc_governance OWNER aitbc_governance;
GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;
```

**Bridge Contract Deployment (Sepolia)**
```bash
# Get Sepolia ETH from faucet (e.g., https://cloud.google.com/application/web3/faucet/ethereum/sepolia)
# Get Infura API key from https://infura.io (free tier)

# Set environment variables
export ETH_NETWORK=sepolia
export ETH_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_KEY
export INFURA_API_KEY=YOUR_INFURA_KEY
export PRIVATE_KEY=0xYOUR_DEPLOYER_WALLET_PRIVATE_KEY

# Deploy
cd /opt/aitbc/contracts
npm install
npx hardhat run scripts/deploy-bridge.js --network sepolia

# Record contract address in env
echo 'BRIDGE_CONTRACT_ADDRESS=0xYOUR_DEPLOYED_ADDRESS' >> /etc/aitbc/blockchain.env
systemctl restart aitbc-exchange.service
```

**Alembic Migration**
```bash
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic upgrade head
```

**Start New Services**
```bash
systemctl enable --now aitbc-governance.service
systemctl enable --now aitbc-exchange.service
systemctl enable --now aitbc-blockchain-rpc.service
systemctl enable --now prometheus prometheus-node-exporter \
  prometheus-redis-exporter prometheus-postgres-exporter
```

**Verify**
```bash
# Check all services
systemctl list-units --type=service --state=running | grep aitbc

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json,sys; d=json.load(sys.stdin)
[print(t['labels']['job'], t['health']) for t in d['data']['activeTargets']]
"

# Check governance
curl http://127.0.0.1:8105/health
curl http://127.0.0.1:8105/v1/governance/status
```

### ✅ Phase 7: WebSocket Push Sync & Follower Node Fixes

**7.1 WebSocket Server (hub-side)**
- ✅ Created `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py` — WebSocket endpoint for real-time block push
  - `GET /rpc/subscribe/ws` — accepts WebSocket connections from follower nodes
  - Validates subscriber has a valid lease (registered via `POST /rpc/subscribe`)
  - Subscribes to gossip topic `blocks.{chain_id}` and streams new blocks to clients
  - Sends periodic pings every 20s for keepalive
  - Handles disconnections and cleans up subscriber registry
- ✅ `app.py` includes `websocket_router` at `/rpc` prefix
- ✅ nginx WebSocket proxy added at `/rpc/subscribe/ws` → `http://127.0.0.1:8202` with `Upgrade` headers and 3600s timeout
- ✅ `aitbc-blockchain-rpc.service` enabled and started (was inactive)

**7.2 WebSocket Client (follower-side)**
- ✅ Implemented `_receive_via_websocket()` in `apps/blockchain-node/src/aitbc_chain/subscription_client.py`
  - Converts hub URL to `wss://` for secure WebSocket connection
  - Sends subscription message via `websocket.send(json.dumps({...}))` (correct `websockets` library API)
  - Filters control messages (confirmation, pings) — only processes messages with `height` field
  - Auto-reconnects on `ConnectionClosed` with 5s backoff
  - Falls back to pull mode on unrecoverable errors
- ✅ Added `websockets==15.0.1` import (already installed)

**7.3 Chain ID Fix**
- ✅ `config.py`: Changed `supported_chains` default from hardcoded `"ait-mainnet"` to `""` — now correctly falls back to `CHAIN_ID` env var (`ait-hub.aitbc.bubuit.net`)
- ✅ Removed stale `/var/lib/aitbc/data/ait-mainnet/` database (12 MB, orphaned from misconfigured chain ID)

**7.4 Adaptive Pull/Push Sync**
- ✅ `_periodic_sync_task()` in `main.py` now accepts `subscription_client` reference
  - Skips periodic pull when WebSocket push is active (`sync_mode == "push"`)
  - Automatically resumes pull sync when WebSocket is unavailable (fallback)
  - Startup behavior: pull runs once on boot before WebSocket connects, then push takes over

**7.5 PostgreSQL Credentials Security**
- ✅ Removed hardcoded PostgreSQL credentials from `apps/blockchain-node/src/aitbc_chain/config.py`
  - `mempool_db_url` now defaults to `""` — requires `MEMPOOL_DB_URL` env var
- ✅ Added `MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:aitbc_mempool@localhost:5432/aitbc_mempool` to `/etc/aitbc/blockchain.env`

**7.6 Blockchain Node Sync Fixes**
- ✅ Fixed `default_peer_rpc_url` in `blockchain.env` to point to hub (`https://hub.aitbc.bubuit.net`)
- ✅ Changed all hub URLs from HTTP to HTTPS in `blockchain.env` (fixes 308 redirect errors)
- ✅ Removed `/rpc` suffix from hub URLs to prevent double `/rpc` in sync requests
- ✅ Fixed genesis block hash validation in `sync.py` — normalizes hashes missing `0x` prefix
- ✅ Fixed double `/rpc` bug in `cli/aitbc_cli/commands/market.py` cancel fallback path

**Result**: Follower node (aitbc3) now syncs via WebSocket push mode with automatic pull fallback. Sync latency reduced from ~30s (periodic poll) to <1s (real-time push).

## 🐛 Known Issues

- **Bridge deposit/withdraw stubs**: Exchange API endpoints `POST /v1/bridge/deposit` and `POST /v1/bridge/withdraw` return stub responses. The bridge monitor service (`aitbc-bridge-monitor.service`) handles actual ETH→AIT processing via deposit detection and AIT transfer submission.
- **Bridge monitor scanning**: Uses web3.py directly via `EthereumRPCClient._get_web3()` for full transaction access, as `get_block()` returns summary data only.
- **AIT/USD price**: Fixed fallback price ($0.01) used; no live market data available for AIT.
- **Grafana disabled**: Grafana 13.0.2 installed but disabled by user to conserve resources. Enable with `systemctl start grafana-server` when monitoring dashboards are needed.
- **No swap**: VPS has 0 swap configured. If memory pressure increases (new services added), consider adding a swap file.
- **Blockchain RPC metrics**: AITBC-specific chain metrics (block height, tx throughput) not yet exposed in `/metrics` — only default Python runtime metrics.
- **Phase 5.3 GPU Optimization**: Skipped — no GPU on this VPS.

## 📚 Documentation Updates

- ✅ `/opt/aitbc/docs/releases/RELEASE_v0.4.14.md` — this file
- ✅ `/etc/prometheus/prometheus.yml` — production scrape config
- ✅ `/etc/prometheus/rules/aitbc_alerts.yml` — alert rules

## 📈 Performance Metrics

### Cache Performance
- **Account balance lookup (DB)**: ~61ms
- **Account balance lookup (cached)**: ~39ms
- **Cache speedup**: ~36% improvement

### Service Workers (corrected for 2-core VPS)
| Service | Before | After |
|---------|--------|-------|
| blockchain-rpc | 4 workers | 1 worker |
| coordinator-api | 4 workers | 1 worker |
| api-gateway | 4 workers | 1 worker |
| governance | 2 workers | 1 worker |

---

**Release Status**: ✅ Released
**Implementation Date**: June 8, 2026
**Next Release**: v0.4.15
