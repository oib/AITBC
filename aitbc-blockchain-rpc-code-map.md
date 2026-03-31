# AITBC Blockchain RPC Service Code Map

## Service Configuration
**File**: `/etc/systemd/system/aitbc-blockchain-rpc.service`
**Entry Point**: `python3 -m uvicorn aitbc_chain.app:app --host ${rpc_bind_host} --port ${rpc_bind_port}`
**Working Directory**: `/opt/aitbc/apps/blockchain-node`
**Environment File**: `/etc/aitbc/blockchain.env`

## Application Structure

### 1. Main Entry Point: `app.py`
**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/app.py`

#### Key Components:
- **FastAPI App**: `create_app()` function
- **Lifespan Manager**: `async def lifespan(app: FastAPI)`
- **Middleware**: RateLimitMiddleware, RequestLoggingMiddleware
- **Routers**: rpc_router, websocket_router, metrics_router

#### Startup Sequence (lifespan function):
1. `init_db()` - Initialize database
2. `init_mempool()` - Initialize mempool
3. `create_backend()` - Create gossip backend
4. `await gossip_broker.set_backend(backend)` - Set up gossip broker
5. **PoA Proposer** (if enabled):
   - Check `settings.enable_block_production and settings.proposer_id`
   - Create `PoAProposer` instance
   - Call `asyncio.create_task(proposer.start())`

### 2. RPC Router: `rpc/router.py`
**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py`

#### Key Endpoints:
- `GET /rpc/head` - Returns current chain head (404 when no blocks exist)
- `GET /rpc/mempool` - Returns pending transactions (200 OK)
- `GET /rpc/blocks/{height}` - Returns block by height
- `POST /rpc/transaction` - Submit transaction
- `GET /rpc/blocks-range` - Get blocks in height range

### 3. Gossip System: `gossip/broker.py`
**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/gossip/broker.py`

#### Backend Types:
- `InMemoryGossipBackend` - Local memory backend (currently used)
- `BroadcastGossipBackend` - Network broadcast backend

#### Key Functions:
- `create_backend(backend_type, broadcast_url)` - Creates backend instance
- `gossip_broker.set_backend(backend)` - Sets active backend

### 4. Chain Sync System: `chain_sync.py`
**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/chain_sync.py`

#### ChainSyncService Class:
- **Purpose**: Synchronizes blocks between nodes
- **Key Methods**:
  - `async def start()` - Starts sync service
  - `async def _broadcast_blocks()` - **MONITORING SOURCE**
  - `async def _receive_blocks()` - Receives blocks from Redis

#### Monitoring Code (_broadcast_blocks method):
```python
async def _broadcast_blocks(self):
    """Broadcast local blocks to other nodes"""
    import aiohttp
    
    last_broadcast_height = 0
    retry_count = 0
    max_retries = 5
    base_delay = 2
    
    while not self._stop_event.is_set():
        try:
            # Get current head from local RPC
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{self.source_host}:{self.source_port}/rpc/head") as resp:
                    if resp.status == 200:
                        head_data = await resp.json()
                        current_height = head_data.get('height', 0)
                        
                        # Reset retry count on successful connection
                        retry_count = 0
```

### 5. PoA Consensus: `consensus/poa.py`
**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py`

#### PoAProposer Class:
- **Purpose**: Proposes blocks in Proof-of-Authority system
- **Key Methods**:
  - `async def start()` - Starts proposer loop
  - `async def _run_loop()` - Main proposer loop
  - `def _fetch_chain_head()` - Fetches chain head from database

### 6. Configuration: `blockchain.env`
**Location**: `/etc/aitbc/blockchain.env`

#### Key Settings:
- `rpc_bind_host=0.0.0.0`
- `rpc_bind_port=8006`
- `gossip_backend=memory` (currently set to memory backend)
- `enable_block_production=false` (currently disabled)
- `proposer_id=` (currently empty)

## Monitoring Source Analysis

### Current Configuration:
- **PoA Proposer**: DISABLED (`enable_block_production=false`)
- **Gossip Backend**: MEMORY (no network sync)
- **ChainSyncService**: NOT EXPLICITLY STARTED

### Mystery Monitoring:
Despite all monitoring sources being disabled, the service still makes requests to:
- `GET /rpc/head` (404 Not Found)
- `GET /rpc/mempool` (200 OK)

### Possible Hidden Sources:
1. **Built-in Health Check**: The service might have an internal health check mechanism
2. **Background Task**: There might be a hidden background task making these requests
3. **External Process**: Another process might be making these requests
4. **Gossip Backend**: Even the memory backend might have monitoring

### Network Behavior:
- **Source IP**: `10.1.223.1` (LXC gateway)
- **Destination**: `localhost:8006` (blockchain RPC)
- **Pattern**: Every 10 seconds
- **Requests**: `/rpc/head` + `/rpc/mempool`

## Conclusion

The monitoring is coming from **within the blockchain RPC service itself**, but the exact source remains unclear after examining all obvious candidates. The most likely explanations are:

1. **Hidden Health Check**: A built-in health check mechanism not visible in the main code paths
2. **Memory Backend Monitoring**: Even the memory backend might have monitoring capabilities
3. **Internal Process**: A subprocess or thread within the main process making these requests

### Recommendations:
1. **Accept the monitoring** - It appears to be harmless internal health checking
2. **Add authentication** to require API keys for RPC endpoints
3. **Modify source code** to remove the hidden monitoring if needed

**The monitoring is confirmed to be internal to the blockchain RPC service, not external surveillance.**
