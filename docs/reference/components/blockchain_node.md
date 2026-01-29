# Blockchain Node – Task Breakdown

## Status (2026-01-29)

- **Stage 1**: ✅ **DEPLOYED** - Blockchain Node successfully deployed on host with RPC API accessible
  - SQLModel-based blockchain with PoA consensus implemented
  - RPC API running on ports 8081/8082 (proxied via /rpc/ and /rpc2/)
  - Mock coordinator on port 8090 (proxied via /v1/)
  - Devnet scripts and observability hooks implemented
  - ✅ **NEW**: Transaction-dependent block creation implemented
  - ✅ **NEW**: Cross-site RPC synchronization implemented
  - Note: SQLModel/SQLAlchemy compatibility issues remain (low priority)

## Stage 1 (MVP) - COMPLETED

- **Project Scaffolding**
  - ✅ Create `apps/blockchain-node/src/` module layout (`types.py`, `state.py`, `blocks.py`, `mempool.py`, `consensus.py`, `rpc.py`, `p2p.py`, `receipts.py`, `settings.py`).
  - ✅ Add `requirements.txt` with FastAPI, SQLModel, websockets, orjson, python-dotenv.
  - ✅ Provide `.env.example` with `CHAIN_ID`, `DB_PATH`, bind addresses, proposer key.

- **State & Persistence**
  - ✅ Implement SQLModel tables for blocks, transactions, accounts, receipts, peers, params.
  - ✅ Set up database initialization and genesis loading.
  - ✅ Provide migration or reset script under `scripts/`.

- **RPC Layer**
  - ✅ Build FastAPI app exposing `/rpc/*` endpoints (sendTx, getTx, getBlock, getHead, getBalance, submitReceipt, metrics).
  - ✅ Implement admin endpoints for devnet (`mintFaucet`, `paramSet`, `peers/add`).

- **Consensus & Block Production**
  - ✅ Implement PoA proposer loop producing blocks at fixed interval.
  - ✅ Integrate mempool selection, receipt validation, and block broadcasting.
  - ✅ Add basic P2P gossip (websocket) for blocks/txs.
  - ✅ **NEW**: Transaction-dependent block creation - only creates blocks when mempool has pending transactions
  - ✅ **NEW**: HTTP polling mechanism to check RPC mempool size every 2 seconds
  - ✅ **NEW**: Eliminates empty blocks from blockchain

- **Cross-Site Synchronization** [NEW]
  - Multi-site deployment with RPC-based sync
  - Transaction propagation between sites
  - ✅ Block synchronization fully implemented (/blocks/import endpoint functional)
  - Status: Active on all 3 nodes with proper validation
  - ✅ Enable transaction propagation between sites
  - ✅ Configure remote endpoints for all nodes (localhost nodes sync with remote)
  - ✅ Integrate sync module into node lifecycle (start/stop)

- **Receipts & Minting**
  - ✅ Wire `receipts.py` to coordinator attestation mock.
  - Mint tokens to miners based on compute_units with configurable ratios.

- **Devnet Tooling**
  - ✅ Provide `scripts/devnet_up.sh` launching bootstrap node and mocks.
  - Document curl commands for faucet, transfer, receipt submission.

## Production Deployment Details

### Multi-Site Deployment
- **Site A (localhost)**: 2 nodes (ports 8081, 8082) - https://aitbc.bubuit.net/rpc/ and /rpc2/
- **Site B (remote host)**: ns3 server (95.216.198.140)
- **Site C (remote container)**: 1 node (port 8082) - http://aitbc.keisanki.net/rpc/
- **Service**: systemd services for blockchain-node, blockchain-node-2, blockchain-rpc
- **Proxy**: nginx routes /rpc/, /rpc2/, /v1/ to appropriate services
- **Database**: SQLite with SQLModel ORM per node
- **Network**: Cross-site RPC synchronization enabled

### Features
- Transaction-dependent block creation (prevents empty blocks)
- HTTP polling of RPC mempool for transaction detection
- Cross-site transaction propagation via RPC polling
- Proper transaction storage in block data with tx_count
- Redis gossip backend for local transaction sharing

### Configuration
- **Chain ID**: "ait-devnet" (consistent across all sites)
- **Block Time**: 2 seconds
- **Cross-site sync**: Enabled, 10-second poll interval
- **Remote endpoints**: Configured per node for cross-site communication

### Issues
- SQLModel/SQLAlchemy compatibility (low priority)
- ✅ Block synchronization fully implemented via /blocks/import endpoint
- Nodes maintain independent chains (by design with PoA)

## Stage 2+ - IN PROGRESS

- 🔄 Upgrade consensus to compute-backed proof (CBP) with work score weighting.
- 🔄 Introduce staking/slashing, replace SQLite with PostgreSQL, add snapshots/fast sync.
- 🔄 Implement light client support and metrics dashboard.

## Recent Updates (2026-01-29)

### Cross-Site Synchronization Implementation
- **Module**: `/src/aitbc_chain/cross_site.py`
- **Purpose**: Enable transaction and block propagation between sites via RPC
- **Features**:
  - Polls remote endpoints every 10 seconds
  - Detects height differences between nodes
  - Syncs mempool transactions across sites
  - ✅ Imports blocks between sites via /blocks/import endpoint
  - Integrated into node lifecycle (starts/stops with node)
- **Status**: ✅ Fully deployed and functional on all 3 nodes
- **Endpoint**: /blocks/import POST with full transaction support
- **Nginx**: Fixed routing to port 8081 for blockchain-rpc-2

### Configuration Updates
```python
# Added to ChainSettings in config.py
cross_site_sync_enabled: bool = True
cross_site_remote_endpoints: list[str] = [
    "https://aitbc.bubuit.net/rpc2",  # Node 2
    "http://aitbc.keisanki.net/rpc"   # Node 3
]
cross_site_poll_interval: int = 10
```

### Current Node Heights
- Local nodes (1 & 2): 771153 (synchronized)
- Remote node (3): 40324 (independent chain)

### Technical Notes
- Each node maintains independent blockchain state
- Transactions can propagate between sites
- Block creation remains local to each node (PoA design)
- Network connectivity verified via reverse proxy
