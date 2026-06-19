# Network Policy Documentation

## Service Exposure Policy

### Localhost-Only Services (Internal)

These services bind to 127.0.0.1 and should not be exposed externally:

| Service | Port | Purpose | Exposure |
|---------|------|---------|----------|
| `aitbc-coordinator-api.service` | 8203 | Main REST API | **Localhost only** |
| `aitbc-blockchain-rpc.service` | 8545 | Blockchain RPC | **Localhost only** |
| `aitbc-marketplace.service` | 8000 | Marketplace API | **Localhost only** |
| `aitbc-governance.service` | 8001 | Governance API | **Localhost only** |
| `aitbc-wallet.service` | 8002 | Wallet API | **Localhost only** |

### Exposed Services (External)

These services are designed to be exposed to external networks:

| Service | Port | Purpose | Exposure |
|---------|------|---------|----------|
| `aitbc-blockchain-p2p.service` | 30333 | P2P networking | **External** (P2P protocol) |
| `aitbc-blockchain-sync.service` | 30334 | Blockchain sync | **External** (sync protocol) |
| `aitbc-miner.service` | 30335 | Mining operations | **External** (mining protocol) |

### Defense-in-Depth Recommendations

For localhost-only services, consider adding additional security:

```ini
# Example for coordinator-api
[Service]
# Existing localhost binding
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8203

# Additional defense-in-depth (optional)
# IPDeny=any  # Deny all external IP connections
# IPAllow=127.0.0.1  # Only allow localhost
```

## Current Service Bindings

### Coordinator API
```ini
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8203
```
✅ **Correct**: Binds to 127.0.0.1 only

### Blockchain Node Services
```ini
# P2P service (exposed)
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.p2p --host 0.0.0.0 --port 30333

# RPC service (localhost only)
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.rpc --host 127.0.0.1 --port 8545

# Sync service (exposed)
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.sync --host 0.0.0.0 --port 30334
```
✅ **Correct**: P2P and sync exposed, RPC localhost-only

### Marketplace Service
```ini
ExecStart=/opt/aitbc/venv/bin/python -m marketplace_service.main --host 127.0.0.1 --port 8000
```
✅ **Correct**: Binds to 127.0.0.1 only

## Firewall Recommendations

### UFW (Uncomplicated Firewall)

```bash
# Allow SSH
ufw allow 22/tcp

# Allow blockchain P2P and sync ports
ufw allow 30333/tcp  # P2P
ufw allow 30334/tcp  # Sync
ufw allow 30335/tcp  # Mining

# Deny all other incoming traffic
ufw default deny incoming
ufw default allow outgoing

# Enable firewall
ufw enable
```

### iptables

```bash
# Allow established connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow blockchain P2P and sync
iptables -A INPUT -p tcp --dport 30333 -j ACCEPT
iptables -A INPUT -p tcp --dport 30334 -j ACCEPT
iptables -A INPUT -p tcp --dport 30335 -j ACCEPT

# Allow localhost
iptables -A INPUT -i lo -j ACCEPT

# Drop everything else
iptables -A INPUT -j DROP
```

## Service Dependencies

### Coordinator API Dependencies
- **Required**: `aitbc-blockchain-node.service` (RPC)
- **Optional**: `redis.service` (when deployed)
- **Network**: Localhost only (127.0.0.1:8203)

### Blockchain Node Dependencies
- **Required**: `postgresql.service` (database)
- **Optional**: `redis.service` (caching)
- **Network**: Mixed (RPC localhost, P2P/sync external)

## Monitoring and Alerting

### Network Connection Monitoring

Monitor for unexpected external connections to localhost-only services:

```bash
# Check for external connections to coordinator-api
ss -tunp | grep :8203 | grep -v 127.0.0.1

# Check for external connections to blockchain RPC
ss -tunp | grep :8545 | grep -v 127.0.0.1
```

### Alert Thresholds

- **Critical**: External connection to localhost-only service
- **Warning**: Unexpected port binding on exposed service
- **Info**: Normal service startup/port binding

## Implementation Status

- ✅ Service binding documentation complete
- ✅ Current service bindings verified
- ✅ Firewall recommendations provided
- ⏳ IPDeny/IPAllow directives not yet implemented (optional)
- ⏳ Firewall rules not yet deployed (DevOps task)
