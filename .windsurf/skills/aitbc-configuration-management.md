# AITBC Configuration Management Skill

## Overview
Specialized skill for managing `/etc/aitbc/` configuration files across multi-node AITBC deployments. Handles environment configuration, consistency validation, and migration procedures.

## Configuration Structure

### File Organization
```
/etc/aitbc/
├── blockchain.env          # Shared blockchain configuration (chains, RPC, sync)
├── node.env                # Node-specific configuration (P2P, proposer ID)
├── production.env          # Production environment variables
├── credentials/            # Keystore and secrets
└── .env.backup            # Legacy configuration backup
```

### File Purposes

**blockchain.env**
- Shared blockchain configuration across nodes
- Chain IDs and supported chains
- RPC binding configuration
- Sync configuration (SYNC_SOURCE_HOST, SYNC_LEADER_HOST)
- Block production settings
- Database and Redis URLs
- API and service port bindings

**node.env**
- Node-specific identity (NODE_ID, p2p_node_id)
- P2P configuration (bind host/port, peers)
- Proposer ID for block production
- Trusted proposers list
- Node-specific host bindings

**production.env**
- Production environment variables
- NODE_ENV, LOG_LEVEL
- Database and Redis URLs
- Security keys (SECRET_KEY, JWT_SECRET)
- Service port configurations
- Monitoring endpoints

## Multi-Node Configuration

### Chain Hub Architecture

**aitbc (Hub for ait-mainnet)**
```bash
SYNC_SOURCE_HOST=aitbc
SYNC_LEADER_HOST=aitbc
SYNC_CHAIN_ID=ait-mainnet
block_production_chains=ait-mainnet
enable_block_production=true
default_peer_rpc_url=http://aitbc1:8006
```

**aitbc1 (Hub for ait-testnet)**
```bash
SYNC_SOURCE_HOST=aitbc1
SYNC_LEADER_HOST=aitbc1
SYNC_CHAIN_ID=ait-testnet
block_production_chains=ait-testnet
enable_block_production=true
default_peer_rpc_url=http://aitbc:8006
```

**gitea-runner (Follower)**
```bash
SYNC_SOURCE_HOST=aitbc1
SYNC_LEADER_HOST=aitbc1
SYNC_CHAIN_ID=ait-testnet
block_production_chains=
enable_block_production=false
```

## Configuration Update Procedures

### Standard Update Process

1. **Update configuration on primary node**
   ```bash
   sudo nano /etc/aitbc/blockchain.env
   ```

2. **Copy to other nodes**
   ```bash
   scp /etc/aitbc/blockchain.env aitbc1:/etc/aitbc/blockchain.env
   scp /etc/aitbc/blockchain.env gitea-runner:/etc/aitbc/blockchain.env
   ```

3. **Node-specific adjustments**
   - Update node.env values per node
   - Adjust block_production_chains and enable_block_production
   - Set correct SYNC_SOURCE_HOST and SYNC_LEADER_HOST

4. **Restart services**
   ```bash
   sudo systemctl restart aitbc-blockchain-node.service
   sudo systemctl restart aitbc-blockchain-rpc.service
   ```

### Chain Hub Reassignment

To change which node is hub for a chain:

1. **Update target node to be hub**
   ```bash
   SYNC_SOURCE_HOST=<target_node>
   SYNC_LEADER_HOST=<target_node>
   SYNC_CHAIN_ID=<chain_id>
   block_production_chains=<chain_id>
   enable_block_production=true
   ```

2. **Update other nodes to follow**
   ```bash
   SYNC_SOURCE_HOST=<target_node>
   SYNC_LEADER_HOST=<target_node>
   SYNC_CHAIN_ID=<chain_id>
   block_production_chains=
   enable_block_production=false
   ```

3. **Restart services on all nodes**

## Configuration Validation

### Consistency Check
```bash
# Check chain configuration across nodes
for node in aitbc aitbc1 gitea-runner; do
  echo "=== $node ==="
  ssh $node "grep -E 'CHAIN_ID|supported_chains|SYNC_LEADER_HOST|SYNC_SOURCE_HOST' /etc/aitbc/blockchain.env"
done
```

### Node Identity Check
```bash
# Verify unique p2p_node_id across nodes
for node in aitbc aitbc1 gitea-runner; do
  echo "=== $node ==="
  ssh $node "grep p2p_node_id /etc/aitbc/node.env"
done
```

### Service Configuration Check
```bash
# Verify systemd units use correct EnvironmentFile
grep -r "EnvironmentFile=/etc/aitbc" /etc/systemd/system/aitbc-*.service
```

## Migration Procedures

### Legacy .env → blockchain.env Migration

**Completed migration steps:**
1. Created blockchain.env from .env content
2. Updated systemd units to use blockchain.env
3. Copied blockchain.env to all nodes
4. Restarted services
5. Backed up legacy .env files

**Verification:**
```bash
# Verify blockchain.env exists on all nodes
for node in aitbc aitbc1 gitea-runner; do
  echo "=== $node ==="
  ssh $node "ls -la /etc/aitbc/blockchain.env"
done

# Verify systemd units use blockchain.env
grep -r "EnvironmentFile=/etc/aitbc/blockchain.env" /opt/aitbc/systemd/*.service
```

### Legacy Path Cleanup

**Remove legacy /opt/aitbc/.env references:**
```bash
# Check for references
grep -r "/opt/aitbc/.env" /opt/aitbc/

# Update any runtime code references
# Example: apps/blockchain-node/fix_env_path.py
```

## Common Configuration Tasks

### Add New Chain
1. Update `supported_chains` on all nodes
2. Set appropriate hub node for the chain
3. Configure block production on hub
4. Configure followers to sync from hub
5. Restart services

### Update RPC Port
1. Change `rpc_bind_port` in blockchain.env
2. Update service port mappings
3. Restart blockchain-rpc service
4. Update any dependent services

### Change Sync Target
1. Update `SYNC_SOURCE_HOST` and `SYNC_LEADER_HOST`
2. Update `default_peer_rpc_url` if needed
3. Restart blockchain-node service
4. Verify sync is working

## Troubleshooting

### Services Not Loading Configuration
```bash
# Check EnvironmentFile paths in systemd units
systemctl show aitbc-blockchain-node.service | grep EnvironmentFile

# Verify file exists and is readable
ls -la /etc/aitbc/blockchain.env

# Check service logs
journalctl -u aitbc-blockchain-node.service -n 50
```

### Configuration Not Applied After Restart
```bash
# Verify systemd daemon reloaded
sudo systemctl daemon-reload

# Check if service uses EnvironmentFile
systemctl cat aitbc-blockchain-node.service | grep EnvironmentFile

# Restart service again
sudo systemctl restart aitbc-blockchain-node.service
```

### Sync Issues After Configuration Change
```bash
# Check sync configuration
grep SYNC_ /etc/aitbc/blockchain.env

# Verify peer connectivity
curl http://<peer_host>:8006/rpc/head

# Check sync logs
journalctl -u aitbc-blockchain-node.service | grep -i sync
```

## Best Practices

1. **Always backup before changes**
   ```bash
   sudo cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.backup.$(date +%Y%m%d)
   ```

2. **Test changes on single node first**
   - Apply change on one node
   - Verify service starts correctly
   - Check logs for errors
   - Then propagate to other nodes

3. **Maintain consistency across nodes**
   - Use the same base blockchain.env
   - Only adjust node-specific values in node.env
   - Verify with consistency checks

4. **Document configuration changes**
   - Note reason for change
   - Record timestamp
   - Update relevant documentation

5. **Use version control for systemd units**
   - Edit files in /opt/aitbc/systemd/
   - Commit changes to git
   - Use link-systemd.sh to apply

## Related Skills
- aitbc-systemd-git-workflow - systemd service management
- aitbc-basic-operations-skill - general node operations
- multi-chain-island-architecture - chain architecture details
- service-port-mapping - port configuration reference
