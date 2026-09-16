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
- AITBC CLI accessible as `aitbc` (`/usr/local/bin/aitbc`)
- Python venv activated for CLI operations
- Services running on ports 8203 (coordinator), 8106 (exchange), 8202 (blockchain RPC), 8102 (marketplace), 8108 (wallet)
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
aitbc version

# Check service health endpoints
curl -s http://localhost:8202/health
curl -s http://localhost:8203/health
curl -s http://localhost:8102/health
```

**If services are not running or dependencies are missing**, see [Blockchain Troubleshooting](aitbc-blockchain-troubleshooting.md) for resolution steps.

## Port Reference

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8202 | Main blockchain node |
| Coordinator API | 8203 | Agent registry, /v1/* routes |
| Marketplace | 8102 | Offers, bids, orders |
| Wallet Daemon | 8108 | Wallet management (localhost only) |
| Exchange API | 8106 | Trading (localhost only) |

## Operations

### CLI Validation
```bash
# Check CLI version
aitbc version

# Check CLI help
aitbc --help
```

### Wallet Operations
```bash
# List wallets
aitbc wallet list

# Check wallet balance
aitbc wallet balance --name genesis

# Create test wallet
aitbc wallet create --name test-wallet
```

### Blockchain Operations
```bash
# Get blockchain status
aitbc blockchain status

# Get blockchain height
aitbc blockchain height

# Get network status
aitbc network status

# Get analytics
aitbc analytics summary
```

### Service Health Checks
```bash
# Check coordinator API (port 8203)
curl -s http://localhost:8203/health

# Check exchange API (port 8106)
curl -s http://localhost:8106/health

# Check blockchain RPC (port 8202)
curl -s http://localhost:8202/health

# Check marketplace (port 8102)
curl -s http://localhost:8102/health

# Check wallet daemon (port 8108)
curl -s http://localhost:8108/health

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
- **Port conflicts:** Check if ports 8202, 8203, 8102, 8108, 8106 are available
- **Database issues:** Verify `/var/lib/aitbc/data/` has proper permissions
- **Keystore issues:** Check `/var/lib/aitbc/keystore/` exists and has correct permissions

### 5. Restart All Services
```bash
# Restart all AITBC services
sudo systemctl restart aitbc-*
```

For detailed troubleshooting, see [Blockchain Troubleshooting](aitbc-blockchain-troubleshooting.md).

## Common Pitfalls

1. **CLI Not Found:** Ensure `aitbc` is on PATH (`/usr/local/bin/aitbc` exists and is executable)
2. **Wallet Not Found:** Check wallet name spelling, verify keystore directory at `/var/lib/aitbc/keystore/`
3. **Service Unreachable:** Verify services are running: `systemctl status aitbc-*`
4. **Port Mismatch:** Coordinator API is on port 8203 (not 9000 or 9001)
5. **Password Required:** Use password from `/var/lib/aitbc/keystore/.genesis_password` for genesis wallet
6. **Wallet Daemon Separate:** Wallet daemon (port 8108) is separate from blockchain RPC (port 8202)

## Verification Checklist
- [ ] CLI responds to `--version` and `--help`
- [ ] Wallet list shows available wallets
- [ ] Balance check returns valid AIT amount
- [ ] Blockchain info shows current height and hash
- [ ] Network status shows peer connections
- [ ] All services (coordinator, exchange, blockchain, marketplace, wallet) return healthy status

## CLI Entry Point

**Canonical CLI:** `aitbc` (`/usr/local/bin/aitbc`, a shell wrapper exec'ing `python -m aitbc_cli.core.main` inside `/opt/aitbc/venv`)

This is the single CLI entry point for all AITBC operations.

**Usage Examples:**
```bash
# Standard operations
aitbc wallet balance --name genesis
aitbc blockchain status
aitbc network status

# Marketplace/GPU operations
aitbc gpu register --gpu-id <gpu_id>
aitbc market offer --service-type ollama --model-or-variant llama2 --price 1.0
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-basic-operations.md`
