# AITBC Basic Operations Skill

## Trigger Conditions
Activate when user requests basic AITBC operations: CLI validation, wallet operations, blockchain status, service health checks, or system verification.

## Purpose
Test and validate AITBC basic CLI functionality, core blockchain operations, wallet operations, and service connectivity.

## Prerequisites
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Python venv activated for CLI operations
- Services running on ports 8011 (coordinator), 8001 (exchange), 8006 (blockchain RPC)
- Working directory: `/opt/aitbc`
- Default test wallet: "genesis" with password from `/var/lib/aitbc/keystore/.genesis_password`

## Operations

### CLI Validation
```bash
# Check CLI version
./aitbc-cli --version

# Check CLI help
./aitbc-cli --help
```

### Wallet Operations
```bash
# List wallets
./aitbc-cli list

# Check wallet balance
./aitbc-cli balance --name genesis

# Create test wallet
./aitbc-cli create --name test-wallet --password "test123"
```

### Blockchain Operations
```bash
# Get blockchain info
./aitbc-cli chain

# Get network status
./aitbc-cli network

# Get analytics
./aitbc-cli analytics --type blocks --limit 10
```

### Service Health Checks
```bash
# Check coordinator API (port 8011)
curl http://localhost:8011/health

# Check exchange API (port 8001)
curl http://localhost:8001/health

# Check blockchain RPC (port 8006)
curl http://localhost:8006/health
```

## Common Pitfalls

1. **CLI Not Found:** Ensure `/opt/aitbc/aitbc-cli` exists and is executable
2. **Wallet Not Found:** Check wallet name spelling, verify keystore directory at `/var/lib/aitbc/keystore/`
3. **Service Unreachable:** Verify services are running: `systemctl status aitbc-*`
4. **Port Mismatch:** Coordinator API is on port 8011 (not 8000)
5. **Password Required:** Use password from `/var/lib/aitbc/keystore/.genesis_password` for genesis wallet

## Verification Checklist
- [ ] CLI responds to `--version` and `--help`
- [ ] Wallet list shows available wallets
- [ ] Balance check returns valid AIT amount
- [ ] Blockchain info shows current height and hash
- [ ] Network status shows peer connections
- [ ] All three services (coordinator, exchange, blockchain) return healthy status

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **Module:** `cli/unified_cli.py` is a module within the CLI tool for marketplace and messaging operations
- **Note:** For marketplace operations, prefer `python3 cli/unified_cli.py` (verified working with 7 bugs fixed)
