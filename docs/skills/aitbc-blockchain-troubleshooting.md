---
name: aitbc-blockchain-troubleshooting
description: Blockchain troubleshooting including sync issues, P2P problems, service failures, data corruption, and blockchain recovery operations
category: troubleshooting
---

# AITBC Blockchain Troubleshooting Skill

## Trigger Conditions
Activate when user requests blockchain troubleshooting: sync issues, P2P problems, service failures, data corruption, or blockchain recovery operations.

## Purpose
Diagnose and troubleshoot AITBC blockchain issues including synchronization failures, P2P network problems, service failures, and data corruption.

## Prerequisites
- SSH access to all nodes (aitbc, aitbc1, gitea-runner)
- Systemd services operational or accessible for debugging
- Log access at `/var/log/aitbc/`
- Data directory at `/var/lib/aitbc/`
- CLI accessible at `/opt/aitbc/aitbc-cli`

## Operations

### 1. Initial Diagnosis
```bash
# Check service status on all nodes
systemctl status aitbc-blockchain-node.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl status aitbc-blockchain-node.service'

# Check blockchain RPC health
curl http://localhost:8006/health
curl http://10.1.223.40:8006/health
curl http://aitbc1:8006/health

# Check P2P network status
netstat -an | grep 7070
ssh aitbc1 'netstat -an | grep 7070'
```

### 2. Blockchain Sync Issues
```bash
# Check blockchain height on all nodes
./aitbc-cli chain
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli chain'
ssh gitea-runner 'cd /opt/aitbc && ./aitbc-cli chain'

# Check mempool status
./aitbc-cli mempool status
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli mempool status'

# Check P2P connections
./aitbc-cli network
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli network'
```

### 2.1 Genesis Block Mismatch Issues

**Symptoms:**
- "Unhandled import case" errors during bulk sync
- Nodes unable to sync blocks for a specific chain
- Different genesis block hashes across nodes

**Diagnosis:**
```bash
# Check genesis block hashes across nodes
sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db "SELECT chain_id, height, hash FROM block WHERE height=0"
ssh aitbc1 'sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db "SELECT chain_id, height, hash FROM block WHERE height=0"'

# Check RPC bootstrap logs
journalctl -u aitbc-blockchain-node.service | grep -i "RPC bootstrap"

# Verify RPC endpoint is accessible
curl http://aitbc1:8006/rpc/genesis_allocations?chain_id=ait-testnet
```

**Solution - Force RPC Bootstrap:**
```bash
# Stop blockchain service
sudo systemctl stop aitbc-blockchain-node.service

# Delete genesis block from database
sqlite3 /var/lib/aitbc/data/<chain_id>/chain.db "DELETE FROM block WHERE chain_id='<chain_id>' AND height=0"

# Restart service to trigger RPC bootstrap
sudo systemctl start aitbc-blockchain-node.service

# Verify RPC bootstrap worked
journalctl -u aitbc-blockchain-node.service | grep -i "RPC bootstrap"
```

**How RPC Bootstrap Works:**
- Nodes attempt RPC bootstrap when genesis block is missing
- Fetches genesis block data (allocations, hash, state_root) from trusted peers
- Creates genesis block using RPC-provided data for consistency
- Falls back to local creation if RPC bootstrap fails

**Configuration Requirements:**
- `default_peer_rpc_url` must be set in blockchain.env
- Points to trusted peer with correct genesis block
- Multiple peers can be configured

### 3. P2P Network Problems
```bash
# Check P2P node IDs
cat /etc/aitbc/.env | grep p2p_node_id
ssh aitbc1 'cat /etc/aitbc/.env | grep p2p_node_id'

# Generate unique node IDs if duplicates found
/opt/aitbc/scripts/utils/generate_unique_node_ids.py

# Restart blockchain services
systemctl restart aitbc-blockchain-p2p.service
ssh aitbc1 'systemctl restart aitbc-blockchain-p2p.service'
```

### 4. Service Failures
```bash
# Check service logs
journalctl -u aitbc-blockchain-node.service -n 100
journalctl -u aitbc-blockchain-p2p.service -n 100
ssh aitbc1 'journalctl -u aitbc-blockchain-node.service -n 100'

# Check application logs
tail -f /var/log/aitbc/blockchain-node.log
tail -f /var/log/aitbc/blockchain-p2p.log
ssh aitbc1 'tail -f /var/log/aitbc/blockchain-node.log'
```

### 5. Data Corruption
```bash
# Check database integrity
sqlite3 /var/lib/aitbc/data/blockchain.db "PRAGMA integrity_check;"

# Check CoW status (Btrfs)
lsattr /var/lib/aitbc

# Disable CoW if enabled
chattr +C /var/lib/aitbc

# Enable WAL mode
sqlite3 /var/lib/aitbc/data/blockchain.db "PRAGMA journal_mode=WAL;"
```

### 6. Recovery Operations
```bash
# Stop blockchain services
systemctl stop aitbc-blockchain-node.service aitbc-blockchain-p2p.service
ssh aitbc1 'systemctl stop aitbc-blockchain-node.service aitbc-blockchain-p2p.service'

# Backup current data
cp -r /var/lib/aitbc/data /var/lib/aitbc/data.backup

# Restore from backup if needed
systemctl stop aitbc-blockchain-node.service
rm -rf /var/lib/aitbc/data/*
cp -r /var/lib/aitbc/data.backup/* /var/lib/aitbc/data/
systemctl start aitbc-blockchain-node.service

# Restart services
systemctl start aitbc-blockchain-node.service aitbc-blockchain-p2p.service
ssh aitbc1 'systemctl start aitbc-blockchain-node.service aitbc-blockchain-p2p.service'
```

### 7. Communication Test
```bash
# Run full communication test
./scripts/blockchain-communication-test.sh --full --debug

# Verify all services are healthy
curl http://localhost:8006/health
curl http://aitbc1:8006/health
curl http://10.1.223.40:8001/health
curl http://10.1.223.40:8011/health

# Check blockchain sync
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain height
NODE_URL=http://aitbc1:8006 ./aitbc-cli blockchain height
```

## Common Pitfalls

1. **Duplicate P2P Node IDs:** Check for duplicate p2p_node_id in `/etc/aitbc/.env` - generate unique IDs
2. **Btrfs CoW Corruption:** Disable CoW on `/var/lib/aitbc` with `chattr +C`
3. **SQLite Corruption:** Enable WAL mode and check database integrity
4. **Port Mismatches:** Coordinator API is on port 8011 (not 8000)
5. **Service Start Order:** Ensure P2P service starts before blockchain-node service
6. **Network Connectivity:** Verify P2P port 7070 is open and accessible
7. **Data Directory Permissions:** Ensure proper permissions on `/var/lib/aitbc/data`

## Verification Checklist
- [ ] All blockchain services running
- [ ] Blockchain heights match across nodes
- [ ] P2P connections established (port 7070)
- [ ] RPC endpoints responding (port 8006)
- [ ] No duplicate P2P node IDs
- [ ] Database integrity check passes
- [ ] CoW disabled on data directory
- [ ] WAL mode enabled for database

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **RPC URL:** Default is `http://localhost:8006`
- **Coordinator API:** Port 8011 (not 8000)
