# Adding gitea-runner as Third Blockchain Node (aitbc2)

## Overview

This document describes the experience of adding `gitea-runner` as a third blockchain node (NODE_ID: `aitbc2`) to the existing AITBC network consisting of `aitbc` and `aitbc1`.

**Date**: April 20, 2026
**Objective**: Add gitea-runner as a 3rd blockchain node to improve network resilience and provide a dedicated CI runner with full blockchain access.

## Network Configuration

### Existing Nodes
- **aitbc** (localhost): `10.1.223.93`, NODE_ID: `aitbc`
- **aitbc1**: `10.1.223.40`, NODE_ID: `aitbc1`

### New Node
- **gitea-runner**: `10.1.223.98`, NODE_ID: `aitbc2`

### Shared Infrastructure
- **Redis Server**: `10.1.223.93:6379` (used for gossip backend)
- **P2P Port**: `7070` (all nodes)
- **RPC Port**: `8006` (all nodes)
- **Chain ID**: `ait-devnet`

## Configuration Steps

### Step 1: Configure Node Identity on gitea-runner

**File**: `/etc/aitbc/node.env`

```bash
# AITBC Node-Specific Environment Configuration
# This file contains variables unique to this node
# DO NOT commit to version control - each node has different values

# Node Identity
NODE_ID=aitbc2

# P2P Configuration
p2p_node_id=aitbc2
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
proposer_id=ait1ytkh0cn8v2a4zjwzyav6854832myf9j7unsse8yntmuwzst4qhtqe9hqdw

# P2P Peers (comma-separated list of peer nodes)
p2p_peers=aitbc:7070,aitbc1:7070

# Trusted Proposers (for follower nodes)
trusted_proposers=
```

### Step 2: Configure Shared Environment on gitea-runner

**File**: `/etc/aitbc/.env`

```bash
# AITBC Environment Configuration
# This file contains shared environment variables
# DO NOT commit to version control

# Database Configuration
DATABASE_URL=sqlite:////var/lib/aitbc/data/chain.db

# Redis Configuration
REDIS_URL=redis://10.1.223.93:6379/0
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379

# Blockchain Configuration
CHAIN_ID=ait-devnet
supported_chains=ait-devnet
BLOCK_TIME=5
enable_block_production=false  # Disable block production to prevent forks

# RPC Configuration
rpc_bind_host=0.0.0.0
rpc_bind_port=8006

# API Configuration
api_host=0.0.0.0
api_port=8000

# Wallet Configuration
wallet_host=0.0.0.0
wallet_port=8003

# Exchange Configuration
exchange_host=0.0.0.0
exchange_port=8001
```

**Key Configuration Decisions**:
- `DATABASE_URL` points to `/var/lib/aitbc/data/chain.db` (not `/var/lib/aitbc/aitbc.db`)
- `CHAIN_ID` set to `ait-devnet` to match existing network
- `supported_chains` set to `ait-devnet` (critical - default is `ait-devnet` but must be explicit)
- `enable_block_production=false` to prevent fork creation (all nodes had same proposer_id)

### Step 3: Add Hostname Resolution

**File**: `/etc/hosts` (on all nodes)

Added the following entries to all three nodes:

```
10.1.223.93  aitbc
10.1.223.40  aitbc1
10.1.223.98  aitbc2  gitea-runner
```

### Step 4: Update P2P Peers on Existing Nodes

**File**: `/etc/aitbc/node.env` on `aitbc` and `aitbc1`

Updated `p2p_peers` to include the new node:

```bash
# On aitbc
p2p_peers=aitbc1:7070,aitbc2:7070

# On aitbc1
p2p_peers=aitbc:7070,aitbc2:7070
```

### Step 5: Add Missing P2P Bind Configuration

**File**: `/etc/aitbc/node.env` (all nodes)

Added missing environment variables that were causing P2P service failures:

```bash
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
```

### Step 6: Update Gossip Backend Configuration

**File**: `/etc/aitbc/.env` (all nodes)

Updated to use shared Redis instance for gossip:

```bash
REDIS_URL=redis://10.1.223.93:6379/0
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
```

### Step 7: Restart P2P Services

```bash
# On all nodes
systemctl restart aitbc-blockchain-p2p.service
systemctl status aitbc-blockchain-p2p.service
```

### Step 8: Copy Blockchain Database

To sync gitea-runner with the existing network, copied the blockchain database from `aitbc`:

```bash
# Stop blockchain node on aitbc
systemctl stop aitbc-blockchain-node.service

# Copy database to gitea-runner
scp /var/lib/aitbc/data/chain.db gitea-runner:/var/lib/aitbc/data/chain.db

# Restart blockchain node on aitbc
systemctl start aitbc-blockchain-node.service

# Start blockchain node on gitea-runner
ssh gitea-runner "systemctl start aitbc-blockchain-node.service"
```

### Step 9: Restart Blockchain Node Services

```bash
# On all nodes
systemctl restart aitbc-blockchain-node.service
```

## Issues Encountered and Resolutions

### Issue 1: P2P Service Restarting Continuously

**Symptom**: `aitbc-blockchain-p2p.service` failed with "invalid int value: ''" for `--port`

**Cause**: Missing `p2p_bind_host` and `p2p_bind_port` environment variables in `node.env`

**Resolution**: Added the missing variables to all nodes' `node.env` files:
```bash
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
```

### Issue 2: CHAIN_ID Mismatch

**Symptom**: gitea-runner blockchain node logs showed "Importing block for chain ait-devnet" while other nodes were on `ait-testnet`

**Initial Misunderstanding**: Initially thought the network was on `ait-testnet` and tried to change gitea-runner to match

**Resolution**: Verified that the existing network was actually on `ait-devnet` and set gitea-runner to match:
```bash
CHAIN_ID=ait-devnet
supported_chains=ait-devnet
```

### Issue 3: Block Creation Causing Forks

**Symptom**: gitea-runner was proposing blocks simultaneously with other nodes, causing "Fork detected" errors

**Cause**: All three nodes had the same `proposer_id`, causing them to all act as proposers and create competing chains

**Resolution**: Disabled block production on gitea-runner by setting:
```bash
enable_block_production=false
```

This makes gitea-runner a follower node that only receives blocks from the network via gossip.

### Issue 4: Database Location Mismatch

**Symptom**: gitea-runner blockchain height remained at 25 despite copying database

**Cause**: `DATABASE_URL` in `.env` was set to `sqlite:////var/lib/aitbc/aitbc.db` but the config uses `db_path` which defaults to `/var/lib/aitbc/data/chain.db`

**Resolution**: Updated `DATABASE_URL` to match the actual database location:
```bash
DATABASE_URL=sqlite:////var/lib/aitbc/data/chain.db
```

### Issue 5: supported_chains Default Value

**Symptom**: Even with `CHAIN_ID=ait-devnet` set, gitea-runner was still using `ait-devnet` from the default `supported_chains` value in config.py

**Cause**: The blockchain node uses `supported_chains` (default: "ait-devnet") to determine which chains to propose blocks on, not just `CHAIN_ID`

**Resolution**: Explicitly set `supported_chains` in `.env`:
```bash
supported_chains=ait-devnet
```

## Verification

### P2P Layer Verification

```bash
# Check P2P service status on all nodes
systemctl status aitbc-blockchain-p2p.service

# Verify P2P connections
# (Check logs for successful peer connections)
journalctl -u aitbc-blockchain-p2p.service -n 50
```

**Result**: All three nodes successfully connected to each other via P2P.

### Blockchain Layer Verification

```bash
# Check blockchain height on all nodes
./aitbc-cli blockchain height
ssh aitbc1 "/opt/aitbc/aitbc-cli blockchain height"
ssh gitea-runner "/opt/aitbc/aitbc-cli blockchain height"
```

**Result**: 
- aitbc: ~4686
- aitbc1: ~4686
- gitea-runner: Syncing via gossip, logs show successful block imports

### Log Verification

```bash
# Check gitea-runner blockchain node logs
ssh gitea-runner "journalctl -u aitbc-blockchain-node.service -n 30 --no-pager"
```

**Expected Log Output**:
```
{"timestamp": "2026-04-20T11:50:12.394675Z", "level": "INFO", "logger": "aitbc_chain.main", "message": "Importing block for chain ait-devnet: 4673"}
{"timestamp": "2026-04-20T11:50:12.521809Z", "level": "INFO", "logger": "aitbc_chain.sync", "message": "Imported block", "height": 4673, "hash": "...", "proposer": "..."}
{"timestamp": "2026-04-20T11:50:12.521913Z", "level": "INFO", "logger": "aitbc_chain.main", "message": "Import result: accepted=True, reason=Appended to chain"}
```

**Result**: gitea-runner successfully importing blocks via gossip with "accepted=True" status.

## Final Status

**P2P Layer**: ✅ Working
- All three nodes connected via P2P
- Peer discovery working correctly
- No connection errors

**Blockchain Layer**: ✅ Working
- gitea-runner syncing blocks via gossip
- Block production disabled to prevent forks
- Logs show successful block imports
- No fork detection errors

**Configuration**: ✅ Complete
- Node identity configured (aitbc2)
- P2P peers configured on all nodes
- Hostname resolution working
- Shared Redis gossip backend configured
- Database location corrected
- Chain ID and supported_chains aligned with network

## Key Learnings

1. **supported_chains is Critical**: The blockchain node uses `supported_chains` to determine which chains to propose blocks on. This must be set explicitly, not just `CHAIN_ID`.

2. **Database Location Matters**: The `DATABASE_URL` in `.env` must match the actual database location used by the config (`db_path` defaults to `/var/lib/aitbc/data/chain.db`).

3. **Proposer ID Conflicts**: All nodes with the same `proposer_id` will propose blocks simultaneously, causing forks. Disable block production on follower nodes.

4. **P2P Bind Configuration**: Missing `p2p_bind_host` and `p2p_bind_port` causes P2P service failures. These must be set in `node.env`.

5. **Environment Variable Loading**: Systemd services load environment variables from `EnvironmentFile` directives. Verify that the correct files are being loaded (`/etc/aitbc/.env` and `/etc/aitbc/node.env`).

## Recommendations

### For Future Node Additions

1. **Create a Configuration Template**: Create a template `node.env` file with all required variables pre-populated.

2. **Automate Hostname Resolution**: Add `/etc/hosts` entries to the provisioning script.

3. **Unique Proposer IDs**: Consider using unique proposer IDs for each node to prevent fork conflicts.

4. **Configuration Validation**: Add a validation script to check that all required environment variables are set correctly before starting services.

5. **Sync Mechanism**: Implement a proper blockchain sync mechanism instead of manual database copying for initial sync.

### For Existing Network

1. **Review Proposer Configuration**: Consider whether all nodes should be proposers or if a subset should be designated.

2. **Monitor Forks**: Add monitoring for fork detection events to identify configuration issues early.

3. **Document Chain IDs**: Clearly document which chain ID the production network uses to avoid confusion.

## References

### Related Documentation
- [Blockchain Synchronization Issues and Fixes](./blockchain_synchronization_issues_and_fixes.md)
- [Multi-Node Blockchain Setup](../../.windsurf/workflows/multi-node-blockchain-setup.md)

### Configuration Files
- `/etc/aitbc/.env` (shared environment)
- `/etc/aitbc/node.env` (node-specific environment)
- `/etc/systemd/system/aitbc-blockchain-node.service`
- `/etc/systemd/system/aitbc-blockchain-p2p.service`

### Source Files
- `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/config.py`
- `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/main.py`
- `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/p2p_network.py`

---

**Last Updated**: 2026-04-20
**Version**: 1.0
**Status**: Complete
