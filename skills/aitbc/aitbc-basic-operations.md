---
name: aitbc-basic-operations
description: Basic AITBC operations including CLI validation, wallet operations, blockchain status, service health checks, and system verification
category: operations
---

# AITBC Basic Operations Skill

**Status:** 🟡 **Procedure Validated** - Procedures accurate if dependencies and services are present

## Trigger Conditions
Activate when user requests basic AITBC operations: CLI validation, wallet operations, blockchain status, service health checks, or system verification.

## Purpose
Test and validate AITBC basic CLI functionality, core blockchain operations, wallet operations, and service connectivity.

## Prerequisites
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Python venv activated for CLI operations
- Services running on ports 8011 (coordinator), 8001 (exchange), 8006 (blockchain RPC), 8102 (marketplace), 8015 (wallet)
- Working directory: `/opt/aitbc`
- Default test wallet: "genesis" with password from `/var/lib/aitbc/keystore/.genesis_password`

## Prerequisites Check
Before proceeding, verify:
```bash
# Check service status
systemctl list-units --state=running | grep aitbc

# Check Python dependencies
source /opt/aitbc/venv/bin/activate && pip list | grep -E "fastapi|click|uvicorn"

# Verify CLI accessible
/opt/aitbc/aitbc-cli --version

# Check service health endpoints
curl -s http://localhost:8006/health
curl -s http://localhost:8011/health
curl -s http://localhost:8102/health
```

**If services are not running or dependencies are missing**, see [Blockchain Troubleshooting](aitbc-blockchain-troubleshooting.md) for resolution steps.

## Port Reference

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8006 | Main blockchain node |
| Coordinator API | 8011 | Agent registry, /v1/* routes |
| Marketplace | 8102 | Offers, bids, orders |
| Wallet Daemon | 8015 | Wallet management (localhost only) |
| Exchange API | 8001 | Trading (localhost only) |

## Operations

### CLI Validation
```bash
# Check CLI version
cd /opt/aitbc && ./aitbc-cli --version

# Check CLI help
cd /opt/aitbc && ./aitbc-cli --help
```

### Wallet Operations
```bash
# List wallets
cd /opt/aitbc && ./aitbc-cli list

# Check wallet balance
cd /opt/aitbc && ./aitbc-cli balance --name genesis

# Create test wallet
cd /opt/aitbc && ./aitbc-cli create --name test-wallet --password "test123"
```

### Blockchain Operations
```bash
# Get blockchain info
cd /opt/aitbc && ./aitbc-cli chain

# Get network status
cd /opt/aitbc && ./aitbc-cli network

# Get analytics
cd /opt/aitbc && ./aitbc-cli analytics --type blocks --limit 10
```

### Service Health Checks
```bash
# Check coordinator API (port 8011)
curl -s http://localhost:8011/health

# Check exchange API (port 8001)
curl -s http://localhost:8001/health

# Check blockchain RPC (port 8006)
curl -s http://localhost:8006/health

# Check marketplace (port 8102)
curl -s http://localhost:8102/health

# Check wallet daemon (port 8015)
curl -s http://localhost:8015/health

# List all running AITBC services
systemctl list-units --type=service --state=running | grep aitbc
```

## Troubleshooting: Services Not Running

If services are not running, follow these steps:

### 1. Check Service Status
```bash
# List all AITBC services
systemctl list-units --type=service | grep aitbc

# Check specific service status
systemctl status aitbc-blockchain-node.service
systemctl status aitbc-blockchain-p2p.service
systemctl status aitbc-coordinator-api.service
systemctl status aitbc-wallet.service
systemctl status aitbc-exchange-api.service
```

### 2. Start Failed Services
```bash
# Start individual services
sudo systemctl start aitbc-blockchain-node.service
sudo systemctl start aitbc-blockchain-p2p.service
sudo systemctl start aitbc-coordinator-api.service
sudo systemctl start aitbc-wallet.service
sudo systemctl start aitbc-exchange-api.service

# Enable services to start on boot
sudo systemctl enable aitbc-blockchain-node.service
sudo systemctl enable aitbc-blockchain-p2p.service
sudo systemctl enable aitbc-coordinator-api.service
```

### 3. Check Service Logs for Errors
```bash
# View recent service logs
journalctl -u aitbc-blockchain-node.service -n 50 --no-pager
journalctl -u aitbc-coordinator-api.service -n 50 --no-pager

# Follow logs in real-time
journalctl -u aitbc-blockchain-node.service -f
```

### 4. Common Service Failure Causes
- **Missing dependencies:** Check Python venv and required packages
- **Configuration errors:** Verify `/etc/aitbc/.env` and `/etc/aitbc/node.env` exist
- **Port conflicts:** Check if ports 8006, 8011, 8102, 8015, 8001 are available
- **Database issues:** Verify `/var/lib/aitbc/data/` has proper permissions
- **Keystore issues:** Check `/var/lib/aitbc/keystore/` exists and has correct permissions

### 5. Restart All Services
```bash
# Restart all AITBC services
sudo systemctl restart aitbc-*
```

For detailed troubleshooting, see [Blockchain Troubleshooting](aitbc-blockchain-troubleshooting.md).

## Common Pitfalls

1. **CLI Not Found:** Ensure `/opt/aitbc/aitbc-cli` exists and is executable
2. **Wallet Not Found:** Check wallet name spelling, verify keystore directory at `/var/lib/aitbc/keystore/`
3. **Service Unreachable:** Verify services are running: `systemctl status aitbc-*`
4. **Port Mismatch:** Coordinator API is on port 8011 (not 9000 or 9001)
5. **Password Required:** Use password from `/var/lib/aitbc/keystore/.genesis_password` for genesis wallet
6. **Wallet Daemon Separate:** Wallet daemon (port 8015) is separate from blockchain RPC (port 8006)

## Verification Checklist
- [ ] CLI responds to `--version` and `--help`
- [ ] Wallet list shows available wallets
- [ ] Balance check returns valid AIT amount
- [ ] Blockchain info shows current height and hash
- [ ] Network status shows peer connections
- [ ] All services (coordinator, exchange, blockchain, marketplace, wallet) return healthy status

## CLI Entry Point

**Canonical CLI:** `/opt/aitbc/aitbc-cli` (wrapper script)

This is the single CLI entry point for all AITBC operations. The wrapper script loads `cli/unified_cli.py` automatically.

**Direct Python Invocation:** `python3 cli/unified_cli.py`

Use direct Python invocation for:
- Marketplace operations (GPU provider registration, trading)
- GPU testing and Ollama operations
- Specific module features requiring direct access

**Usage Examples:**
```bash
# Standard operations (use wrapper)
/opt/aitbc/aitbc-cli balance --name genesis
/opt/aitbc/aitbc-cli chain
/opt/aitbc/aitbc-cli network

# Marketplace/GPU operations (use direct Python)
python3 cli/unified_cli.py market gpu-provider-register --wallet genesis --gpu-model llama2
python3 cli/unified_cli.py ollama gpu-test --wallet genesis --model llama2
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-basic-operations.md`
