---
name: aitbc-blockchain-troubleshooting
description: Blockchain troubleshooting including sync issues, P2P problems, service failures, data corruption, and blockchain recovery operations
category: troubleshooting
---

# AITBC Blockchain Troubleshooting Skill

**Status:** 🟢 **Evergreen Reference** - Troubleshooting procedures valid regardless of service state

## Trigger Conditions
Activate when user requests blockchain troubleshooting: sync issues, P2P problems, service failures, data corruption, or blockchain recovery operations.

## Purpose
Diagnose and troubleshoot AITBC blockchain issues including synchronization failures, P2P network problems, service failures, and data corruption.

## Prerequisites
- SSH access to all nodes (aitbc, aitbc1, gitea-runner)
- Systemd services operational or accessible for debugging
- Log access via `journalctl`
- Data directory at `/var/lib/aitbc/`
- CLI accessible at `/opt/aitbc/aitbc-cli`

## Prerequisites Check
Before proceeding, verify:
```bash
# Check SSH connectivity
ssh aitbc1 'echo "SSH to aitbc1 working"'
ssh gitea-runner 'echo "SSH to gitea-runner working"'

# Check service status on all nodes
systemctl list-units --state=running | grep aitbc
ssh aitbc1 'systemctl list-units --state=running | grep aitbc'
ssh gitea-runner 'systemctl list-units --state=running | grep aitbc'

# Verify CLI accessible
/opt/aitbc/aitbc-cli --version

# Check data directory
ls -la /var/lib/aitbc/
```

## Port Reference

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8006 | Main blockchain API + messaging |
| Coordinator API | 8011 | Agent registry |
| P2P Network | 7070 | Blockchain peer-to-peer |
| Marketplace | 8102 | Marketplace operations |

## Operations

### 1. Initial Diagnosis
```bash
# Check service status on all nodes
systemctl status aitbc-blockchain-node.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl status aitbc-blockchain-node.service'

# Check blockchain RPC health
curl -s http://localhost:8006/health
curl -s http://aitbc1:8006/health

# Check P2P network status
ss -tlnp | grep 7070
ssh aitbc1 'ss -tlnp | grep 7070'
```

### 2. Blockchain Sync Issues
```bash
# Check blockchain height on all nodes
cd /opt/aitbc && ./aitbc-cli chain
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli chain'
ssh gitea-runner 'cd /opt/aitbc && ./aitbc-cli chain'

# Check mempool status
cd /opt/aitbc && ./aitbc-cli mempool status
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli mempool status'

# Check P2P connections
cd /opt/aitbc && ./aitbc-cli network
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
curl -s http://aitbc1:8006/rpc/genesis_allocations?chain_id=ait-testnet
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
journalctl -u aitbc-blockchain-node.service -f  # Follow mode
ssh aitbc1 'journalctl -u aitbc-blockchain-node.service -f'
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
# Verify all services are healthy
curl -s http://localhost:8006/health
curl -s http://aitbc1:8006/health
curl -s http://localhost:8011/health
curl -s http://localhost:8102/health

# Check blockchain sync
cd /opt/aitbc && ./aitbc-cli chain
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli chain'
```

### 8. GPU Detection Validation

**Purpose:** Verify GPU availability for AI operations and mining.

**Check GPU Status:**
```bash
# Check NVIDIA GPU availability
nvidia-smi

# Check GPU driver version
nvidia-smi --query-gpu=driver_version --format=csv,noheader

# Check CUDA version
nvidia-smi --query-gpu=cuda_version --format=csv,noheader

# Check GPU memory usage
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

**Troubleshooting GPU Issues:**

**Symptoms:**
- `nvidia-smi: command not found`
- `Failed to get GPU info: [Errno 2] No such file or directory: 'nvidia-smi'`
- GPU not detected by AITBC services

**Diagnosis:**
```bash
# Check if NVIDIA drivers are loaded
lsmod | grep nvidia

# Check if nvidia-smi is in PATH
which nvidia-smi

# Check if nvidia-smi is installed but not in PATH
find /usr -name nvidia-smi 2>/dev/null

# Check if container/VM has GPU passthrough
lspci | grep -i nvidia

# Check NVIDIA driver version
cat /proc/driver/nvidia/version 2>/dev/null || echo "NVIDIA driver not loaded"
```

**Solutions:**

**1. Install NVIDIA Drivers (if missing):**
```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install nvidia-driver-535 nvidia-cuda-toolkit

# Reboot after installation
sudo reboot
```

**2. Fix PATH Issues:**
```bash
# Add NVIDIA tools to PATH if installed in non-standard location
export PATH=/usr/local/cuda/bin:$PATH
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
```

**3. Check Container/VM GPU Passthrough:**
```bash
# If running in Docker, ensure GPU is passed through
docker run --gpus all ...

# If running in VM, check GPU passthrough configuration
# This requires hypervisor-level configuration
```

**4. Verify GPU Access for AITBC Services:**
```bash
# Check if AITBC services have GPU access
systemctl status aitbc-miner.service | grep -i gpu

# Check miner logs for GPU detection
journalctl -u aitbc-miner.service | grep -i gpu

# Test GPU with simple CUDA program
nvidia-smi --query-gpu=name --format=csv,noheader
```

**Common GPU Issues:**
1. **NVIDIA Drivers Not Installed:** Install appropriate NVIDIA drivers for your GPU
2. **nvidia-smi Not in PATH:** Add CUDA bin directory to PATH
3. **GPU Passthrough Not Configured:** Configure GPU passthrough in container/VM
4. **Driver Version Mismatch:** Ensure driver version matches CUDA toolkit version
5. **GPU Already in Use:** Check if other processes are using the GPU
6. **Insufficient GPU Memory:** Check available GPU memory with `nvidia-smi`

**Verification:**
```bash
# Verify GPU is accessible
nvidia-smi

# Verify AITBC can detect GPU
cd /opt/aitbc && ./aitbc-cli mining gpu-status 2>/dev/null || echo "GPU status command not available"

# Check miner logs for GPU detection
journalctl -u aitbc-miner.service -n 20 | grep -i gpu
```

## Common Pitfalls

1. **Duplicate P2P Node IDs:** Check for duplicate p2p_node_id in `/etc/aitbc/.env` - generate unique IDs
2. **Btrfs CoW Corruption:** Disable CoW on `/var/lib/aitbc` with `chattr +C`
3. **SQLite Corruption:** Enable WAL mode and check database integrity
4. **Port Mismatches:** Coordinator API is on port 8011 (not 9001)
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

## CLI Entry Point

**Canonical CLI:** `/opt/aitbc/aitbc-cli` (wrapper script)

This is the single CLI entry point for all AITBC operations. The wrapper script loads `cli/unified_cli.py` automatically.

**Usage Examples:**
```bash
# All CLI operations (use wrapper)
/opt/aitbc/aitbc-cli chain
/opt/aitbc/aitbc-cli network
/opt/aitbc/aitbc-cli mempool status
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-blockchain-troubleshooting.md`
