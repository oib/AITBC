# Multi-Chain Architecture
Understanding AITBC's parallel chain management system.

## Overview

AITBC supports running multiple blockchain chains simultaneously through the MultiChainManager. This enables:
- **Horizontal scaling**: Separate chains for different use cases
- **Isolation**: Chain-specific databases prevent cross-contamination
- **Flexibility**: Support for DEFAULT, BILATERAL, and MICRO chain types
- **Resource efficiency**: Shared RPC/P2P ports with chain routing

## Chain Types

### DEFAULT Chain
- **Purpose**: Main chain for the island/network
- **Behavior**: Always running, initialized at startup
- **Use case**: Primary blockchain for production transactions

### BILATERAL Chain
- **Purpose**: Chain between two specific parties
- **Behavior**: Started on-demand, can be stopped
- **Use case**: Private trading channels, settlement chains

### MICRO Chain
- **Purpose**: Small chain for specific use cases
- **Behavior**: Started on-demand, can be stopped
- **Use case**: Temporary workspaces, test chains, isolated transactions

## MultiChainManager API

### Initialization

```python
from aitbc_chain.network.multi_chain_manager import create_multi_chain_manager
from pathlib import Path

# Create manager with default chain
manager = create_multi_chain_manager(
    default_chain_id="ait-mainnet",
    base_db_path=Path("/var/lib/aitbc/data/ait-mainnet"),
    base_rpc_port=8006,
    base_p2p_port=7070
)
```

### Chain Lifecycle

#### Start a Chain

```python
# Start a micro chain
success = await manager.start_chain(
    chain_id="my-micro-chain",
    chain_type=ChainType.MICRO
)
```

#### Stop a Chain

```python
# Stop a running chain
success = await manager.stop_chain(chain_id="my-micro-chain")
```

#### Get Chain Status

```python
# Get status of specific chain
chain = manager.get_chain_status("my-micro-chain")
if chain:
    print(f"Status: {chain.status}")
    print(f"RPC Port: {chain.rpc_port}")
    print(f"DB Path: {chain.db_path}")
```

#### List Active Chains

```python
# Get all running chains
active_chains = manager.get_active_chains()
for chain in active_chains:
    print(f"{chain.chain_id}: {chain.status}")
```

### Chain Synchronization

```python
# Sync a specific chain to highest block
success = manager.sync_chain("my-micro-chain")
```

## Chain Instance Structure

Each chain instance maintains:

```python
@dataclass
class ChainInstance:
    chain_id: str              # Unique identifier
    chain_type: ChainType      # DEFAULT, BILATERAL, or MICRO
    status: ChainStatus        # STOPPED, STARTING, RUNNING, STOPPING, ERROR
    db_path: Path              # Path to chain database
    rpc_port: int              # RPC server port
    p2p_port: int              # P2P service port
    started_at: Optional[float]  # Unix timestamp when started
    stopped_at: Optional[float] # Unix timestamp when stopped
    error_message: Optional[str] # Error details if in ERROR state
```

## Port Allocation

- **Shared ports**: All chains share base RPC and P2P ports
- **No separate allocation**: Ports are not incremented per chain
- **Chain routing**: Chain ID used to route requests to correct chain
- **Base ports**: Configurable (default: RPC 8006, P2P 7070)

## Database Structure

```
/var/lib/aitbc/data/
├── ait-mainnet/          # DEFAULT chain
│   └── chain.db
├── my-micro-chain/       # MICRO chain
│   └── chain.db
└── bilateral-trading/    # BILATERAL chain
    └── chain.db
```

Each chain has its own database directory for complete isolation.

## Chain Status States

| State | Description | Transitions |
|-------|-------------|-------------|
| STOPPED | Chain is not running | → STARTING |
| STARTING | Chain is initializing | → RUNNING or ERROR |
| RUNNING | Chain is operational | → STOPPING or ERROR |
| STOPPING | Chain is shutting down | → STOPPED |
| ERROR | Chain encountered error | Manual intervention required |

## Health Monitoring

The MultiChainManager runs background health checks:

```python
async def _chain_health_check(self):
    """Check health of chain instances"""
    while self.running:
        # Check for chains in error state
        for chain_id, chain in list(self.chains.items()):
            if chain.status == ChainStatus.ERROR:
                logger.warning(f"Chain {chain_id} in error state: {chain.error_message}")
        
        await asyncio.sleep(60)  # Check every minute
```

## Configuration

### Environment Variables

```bash
# Base chain configuration
CHAIN_ID=ait-mainnet              # Default chain ID
BASE_DB_PATH=/var/lib/aitbc/data # Base database path
BASE_RPC_PORT=8006               # Base RPC port
BASE_P2P_PORT=7070               # Base P2P port
```

### Multi-Chain Support in blockchain-node.md

The blockchain node supports multiple chains via the `supported_chains` environment variable:

```bash
# In .env
supported_chains=ait-mainnet,ait-testnet
```

Each chain requires its own genesis file in `data/<chain_id>/genesis.json`.

## Cross-Chain Operations

### Cross-Chain Sync

The `CrossChainSync` class provides synchronization between chains:

```python
from aitbc_chain.cross_chain import CrossChainSync

sync = CrossChainSync(chains=["ait-mainnet", "ait-testnet"])
await sync.test_synchronization()
```

### Multi-Chain Consensus

The `MultiChainConsensus` class handles consensus across chains:

```python
from aitbc_chain.cross_chain import MultiChainConsensus

consensus = MultiChainConsensus(chains=["ait-mainnet", "ait-testnet"])
await consensus.test_consensus_mechanism()
```

## Implementation

The multi-chain system is implemented in:
- `apps/blockchain-node/src/aitbc_chain/network/multi_chain_manager.py` - Core MultiChainManager
- `apps/blockchain-node/src/aitbc_chain/cross_chain.py` - Cross-chain sync and consensus

## Use Cases

### 1. Development and Testing
- Separate testnet chain for development
- Isolated micro-chains for feature testing
- Parallel testing without affecting mainnet

### 2. Private Trading Channels
- Bilateral chains for OTC trading
- Isolated settlement chains
- Privacy-preserving transactions

### 3. Multi-Tenant Architecture
- Separate chains per organization
- Tenant-specific micro-chains
- Resource isolation and security

### 4. Geographic Distribution
- Regional chains for low latency
- Cross-region sync via gossip
- Local compliance and regulation

## Best Practices

1. **Chain naming**: Use descriptive chain IDs (e.g., `org1-trading`, `dev-test-3`)
2. **Database management**: Regular backups of chain databases
3. **Port planning**: Ensure base ports don't conflict with other services
4. **Monitoring**: Track chain status and health metrics
5. **Cleanup**: Stop unused chains to free resources

## Troubleshooting

### Chain fails to start
- Check database path permissions
- Verify base ports are not in use
- Review error logs: `journalctl -u aitbc-blockchain-node -f`

### Chain in ERROR state
- Check `error_message` in ChainInstance
- Verify database integrity
- Restart chain after fixing issue

### Sync issues between chains
- Verify gossip backend (Redis) is running
- Check network connectivity between nodes
- Review chain health status

## Next

- [Networking](./6_networking.md) - P2P networking
- [Consensus](./4_consensus.md) - Consensus mechanism
- [Configuration](./2_configuration.md) - Node configuration
