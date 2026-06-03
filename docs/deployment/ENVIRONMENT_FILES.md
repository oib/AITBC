# AITBC Environment Files Documentation

This document describes the three main environment configuration files used by AITBC services, their purposes, contents, and dependencies.

## Overview

| File | Location | Purpose | Security Level |
|------|----------|---------|----------------|
| `blockchain.env` | `/etc/aitbc/blockchain.env` | Blockchain network configuration | Public (non-sensitive) |
| `node.env` | `/etc/aitbc/node.env` | Node identity and service configuration | Semi-private (contains some secrets) |
| `blockchain-secrets.env` | `/etc/aitbc/blockchain-secrets.env` | Shared cluster authentication secrets | Private (sensitive) |

---

## 1. blockchain.env

**Location:** `/etc/aitbc/blockchain.env`

**Purpose:** Public blockchain network configuration for joining an island. This file contains all non-sensitive settings needed to connect to a blockchain network, including RPC settings, P2P peers, chain IDs, and database paths.

**Security Level:** Public - Can be shared publicly (e.g., via hub website) as it contains no secrets.

**Source:** Downloaded from hub's public endpoint: `https://hub.aitbc.bubuit.net/agent/blockchain.env`

### Key Sections

#### Node Profiles
```bash
BLOCKCHAIN_MODE=follower          # Node role: follower or hub
MARKET_ROLE=shop                  # Marketplace role: customer or shop
HARDWARE_PROFILE=gpu             # Hardware capabilities: gpu or nogpu
```
- **Used by:** Setup scripts, service initialization
- **Why:** Determines which services run on this node based on its role in the network

#### Chain Configuration
```bash
CHAIN_ID=ait-hub.aitbc.bubuit.net           # Unique chain identifier
SUPPORTED_CHAINS=ait-hub.aitbc.bubuit.net   # Chains this node supports
HUB_DISCOVERY_URL=hub.aitbc.bubuit.net       # Hub URL for discovery
```
- **Used by:** Blockchain node, wallet daemon, transaction service
- **Why:** Identifies which blockchain network the node participates in

#### RPC Configuration
```bash
RPC_BIND_HOST=0.0.0.0               # RPC bind address
RPC_BIND_PORT=8202                  # RPC bind port
BLOCKCHAIN_RPC_URL=http://localhost:8202  # Local RPC URL
HUB_HERMES_URL=https://hub.aitbc.bubuit.net/api/v1/hermes  # Hub Hermes endpoint
```
- **Used by:** Blockchain RPC service, wallet daemon, CLI
- **Why:** Configures how services communicate with the blockchain and hub

#### P2P Configuration
```bash
p2p_bind_host=0.0.0.0
p2p_bind_port=8200
p2p_node_id=node-19b909970eeb4a6a87865dbb92c4b5dc
p2p_peers=hub.aitbc.bubuit.net:8200
genesis_node=https://hub.aitbc.bubuit.net
```
- **Used by:** P2P service, blockchain sync
- **Why:** Enables peer-to-peer communication and block synchronization

#### Genesis Configuration
```bash
GENESIS_ADDRESS=ait1db5247d03ca2e40f3995a583b2c097ab703efd4d
```
- **Used by:** Hermes transaction service, coin request execution
- **Why:** Address of the genesis wallet that signs coin transactions (only on hub)

#### Sync Configuration
```bash
default_peer_rpc_url=https://hub.aitbc.bubuit.net
PERIODIC_SYNC_ENABLED=true
PERIODIC_SYNC_INTERVAL=30
SUBSCRIPTION_ENABLED=true
SUBSCRIPTION_TRANSPORT=redis
LEASE_DURATION=3600
```
- **Used by:** Blockchain node (follower mode)
- **Why:** Configures how followers sync blocks from the hub

#### Database & Keystore
```bash
db_path=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db
keystore_path=/var/lib/aitbc/keystore
keystore_password_file=/var/lib/aitbc/keystore/.password
```
- **Used by:** Blockchain node, wallet daemon
- **Why:** Storage locations for blockchain data and wallet keys

#### Mempool Configuration
```bash
MEMPOOL_BACKEND=database
MEMPOOL_DB_URL=postgresql+psycopg2://aitbc_mempool:aitbc_mempool_password@localhost:5432/aitbc_mempool
```
- **Used by:** Mempool service
- **Why:** Database connection for transaction pool

### Services That Load This File
- `aitbc-blockchain-node.service`
- `aitbc-blockchain-rpc.service`
- `aitbc-wallet.service`
- `aitbc-hermes.service`
- CLI commands (`aitbc`)

---

## 2. node.env

**Location:** `/etc/aitbc/node.env`

**Purpose:** Node-specific identity and service configuration. Contains settings that identify this specific node and configure agent services.

**Security Level:** Semi-private - Contains some secrets (API keys) but not highly sensitive cryptographic keys.

**Source:** Created during node setup, may be customized per node.

### Key Sections

#### Node Identity
```bash
NODE_ID=node-aitbc3-0b7a8bda        # Unique node identifier
ISLAND_ID=ait-hub.aitbc.bubuit.net-island  # Island membership
CHAIN_ID=ait-hub.aitbc.bubuit.net   # Must match blockchain.env
NODE_ROLE=follower                  # Node role: follower or genesis
```
- **Used by:** All AITBC services
- **Why:** Identifies this node in the network and determines its capabilities

#### P2P Configuration
```bash
P2P_BIND_PORT=8200                  # Must match blockchain.env
```
- **Used by:** P2P service
- **Why:** Ensures consistent port configuration across services

#### Hermes Polling Configuration
```bash
ENABLE_HERMES_POLLING=true
HERMES_AGENT_IDS=owl-aitbc3
HERMES_COORDINATOR_URL=http://localhost:8107
HERMES_SERVICE_URL=http://localhost:8103
HERMES_AGENT_ID=owl-aitbc3
SECRET_KEY=8598095866d24aa8bcdf5c11fe9cb0ea6ece8c5868af6ee95732fe41dfe8de5c
COORDINATOR_API_KEY=8598095866d24aa8bcdf5c11fe9cb0ea6ece8c5868af6ee95732fe41dfe8de5c
```
- **Used by:** Hermes polling daemon, Agent Coordinator, Hermes service
- **Why:** Configures agent message polling and authentication

**Note:** The `SECRET_KEY` and `COORDINATOR_API_KEY` in this file should match the hub's shared secrets for authentication.

### Services That Load This File
- `aitbc-hermes.service`
- `aitbc-agent-coordinator.service`
- `aitbc-agent-daemon.service`
- Hermes polling daemon

---

## 3. blockchain-secrets.env

**Location:** `/etc/aitbc/blockchain-secrets.env`

**Purpose:** Shared cluster authentication secrets. Contains API keys and secrets that must match across all nodes in the same island for authentication.

**Security Level:** Private - Contains sensitive authentication secrets. Should be protected with file permissions (600).

**Source:** Downloaded from hub's public endpoint (the keys themselves are public for the open island): `https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env`

### Contents

```bash
# Shared cluster secrets for the ait-hub.aitbc.bubuit.net open island
COORDINATOR_API_KEY=8598095866d24aa8bcdf5c11fe9cb0ea6ece8c5868af6ee95732fe41dfe8c
SECRET_KEY=8598095866d24aa8bcdf5c11fe9cb0ea6ece8c5868af6ee95732fe41dfe8de5c
```

#### COORDINATOR_API_KEY
- **Used by:** Wallet daemon, Hermes service, Agent Coordinator
- **Purpose:** Authenticates requests to the Agent Coordinator API
- **Why:** Ensures only authorized nodes can submit agent messages and execute coin requests

#### SECRET_KEY
- **Used by:** Hermes service, Agent Coordinator
- **Purpose:** JWT signing and message authentication
- **Why:** Secures agent-to-agent communication and validates message integrity

### Services That Load This File
- `aitbc-wallet.service`
- `aitbc-hermes.service`
- `aitbc-blockchain-rpc.service` (if needed for authenticated endpoints)

### Security Notes
- **File permissions:** Should be `600` (owner read/write only)
- **Distribution:** For open islands, these keys are public (downloadable from hub)
- **Private islands:** Should use unique, non-public keys generated during setup

---

## Environment File Loading Order

Systemd services load environment files in the order specified in the `[Service]` section. Later files can override earlier ones.

**Example (aitbc-wallet.service):**
```ini
EnvironmentFile=/etc/aitbc/blockchain.env
EnvironmentFile=/etc/aitbc/blockchain-secrets.env
EnvironmentFile=/etc/aitbc/node.env
```

**Loading order:**
1. `blockchain.env` - Base blockchain configuration
2. `blockchain-secrets.env` - Authentication secrets (may override blockchain.env if duplicates exist)
3. `node.env` - Node-specific settings (highest priority)

---

## Service Dependencies

### Blockchain Node Services
- **aitbc-blockchain-node.service:** Loads `blockchain.env`, `node.env`
- **aitbc-blockchain-rpc.service:** Loads `blockchain.env`, `blockchain-secrets.env`, `node.env`

### Agent Services
- **aitbc-hermes.service:** Loads `blockchain.env`, `node.env`
- **aitbc-agent-coordinator.service:** Loads `node.env`
- **aitbc-agent-daemon.service:** Loads `node.env`

### Wallet Service
- **aitbc-wallet.service:** Loads `blockchain.env`, `blockchain-secrets.env`, `node.env`

### CLI
- **aitbc CLI:** Loads `blockchain.env` and `node.env` via `get_config()`

---

## Common Issues

### Issue: Service fails to start with "Failed to load environment files"
**Cause:** One of the specified `EnvironmentFile` paths doesn't exist
**Solution:** Ensure all referenced files exist at the specified paths

### Issue: "COORDINATOR_API_KEY not set" error
**Cause:** `blockchain-secrets.env` not loaded or missing
**Solution:** Add `EnvironmentFile=/etc/aitbc/blockchain-secrets.env` to the service file

### Issue: "unsupported chain_id" error
**Cause:** `SUPPORTED_CHAINS` in blockchain.env doesn't match actual chain
**Solution:** Ensure `SUPPORTED_CHAINS` matches the actual chain ID (e.g., `ait-hub.aitbc.bubuit.net`)

### Issue: Follower can't execute coin requests
**Cause:** Missing `HUB_HERMES_URL` in blockchain.env or invalid `COORDINATOR_API_KEY`
**Solution:** Add `HUB_HERMES_URL=https://hub.aitbc.bubuit.net/api/v1/hermes` and ensure API key matches hub

---

## Setup Checklist

When setting up a new node:

1. **Download blockchain.env from hub:**
   ```bash
   curl -o /etc/aitbc/blockchain.env https://hub.aitbc.bubuit.net/agent/blockchain.env
   ```

2. **Download blockchain-secrets.env from hub:**
   ```bash
   curl -o /etc/aitbc/blockchain-secrets.env https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env
   chmod 600 /etc/aitbc/blockchain-secrets.env
   ```

3. **Create node.env with unique identity:**
   ```bash
   cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
   # Edit NODE_ID to be unique
   ```

4. **Verify all files exist:**
   ```bash
   ls -la /etc/aitbc/blockchain.env /etc/aitbc/node.env /etc/aitbc/blockchain-secrets.env
   ```

5. **Restart services:**
   ```bash
   systemctl daemon-reload
   systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc aitbc-wallet aitbc-hermes
   ```

6. **Verify connectivity:**
   ```bash
   curl https://hub.aitbc.bubuit.net/rpc/health
   ```
