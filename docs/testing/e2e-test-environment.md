# E2E Test Environment Setup

**Version:** 1.0
**Date:** 2026-05-11
**Status:** Draft
**Purpose:** Define test environment setup and data management for E2E testing

## Overview

This document defines the infrastructure requirements, service configuration, and test data management for end-to-end testing.

## Infrastructure Requirements

### Hardware
- **Minimum:** 4 CPU cores, 16GB RAM, 100GB storage
- **Recommended:** 8 CPU cores, 32GB RAM, 500GB storage
- **GPU:** NVIDIA GPU with CUDA support (for miner testing)

### Software
- **Operating System:** Debian stable (bookworm)
- **Python:** 3.13 or 3.14
- **PostgreSQL:** 15 or later
- **Redis:** 7 or later

## Services Required

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| Coordinator API | 8011 | Job management | Required |
| Blockchain Node | 8080 | Blockchain RPC | Required |
| Wallet Daemon | 8081 | Wallet management | Required |
| GPU Miner | - | Job processing | Required |
| Marketplace | 8102 | Service marketplace | Required |
| Exchange | 8082 | Trading platform | Required |
| Agent Coordinator | 8011 | Agent management | Required |
| PostgreSQL | 5432 | Database | Required |
| Redis | 6379 | Cache | Required |

## Service Orchestration (Systemd)

AITBC uses systemd for service orchestration. Services are managed via systemd unit files.

### Starting Services

```bash
# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Start Redis
sudo systemctl start redis
sudo systemctl enable redis

# Start AITBC services
sudo systemctl start aitbc-blockchain-node
sudo systemctl start aitbc-coordinator-api
sudo systemctl start aitbc-marketplace
sudo systemctl start aitbc-exchange

# Check service status
sudo systemctl status aitbc-blockchain-node
sudo systemctl status aitbc-coordinator-api
sudo systemctl status aitbc-marketplace
```

### Service Health Checks

```bash
# Check coordinator API
curl -s http://localhost:8011/v1/health

# Check blockchain node
curl -s http://localhost:8080/v1/health

# Check marketplace
curl -s http://localhost:8102/v1/health
```

## Configuration

### Environment Variables
```bash
# Coordinator API
COORDINATOR_URL=http://localhost:8011
CLIENT_API_KEY=test-api-key
ADMIN_API_KEY=test-admin-key

# Blockchain
BLOCKCHAIN_URL=http://localhost:8080
BLOCKCHAIN_DATA_DIR=/tmp/blockchain-test

# Wallet
WALLET_DAEMON_URL=http://localhost:8081
WALLET_DATA_DIR=/tmp/wallet-test

# Marketplace
MARKETPLACE_URL=http://localhost:8102

# Database
POSTGRES_URL=postgresql://aitbc:test@localhost:5432/aitbc_test
REDIS_URL=redis://localhost:6379/0
```

## Test Data Management

### Fixtures

**User Fixtures:**
- Regular user
- Admin user
- Miner user
- Agent user

**Wallet Fixtures:**
- Pre-funded wallets
- Empty wallets
- Wallets with staked tokens

**Job Fixtures:**
- Simple inference job
- Complex inference job
- Confidential job
- Batch jobs

**Blockchain Fixtures:**
- Genesis block
- Pre-populated accounts
- Sample transactions

### Data Cleanup

**Before Each Test:**
- Reset database to known state
- Clear blockchain test data
- Reset cache

**After Each Test:**
- Clean up created resources
- Reset service states
- Verify no data leaks

## Appendix

### A. Service Startup Order

1. PostgreSQL
2. Redis
3. Blockchain Node
4. Wallet Daemon
5. Coordinator API
6. Marketplace
7. Exchange
8. GPU Miner
9. Agent Coordinator

### B. Test Data Examples

**Sample User:**
```json
{
  "user_id": "test-user-001",
  "email": "test@example.com",
  "role": "user",
  "wallet_address": "ait1testuser001"
}
```

**Sample Job:**
```json
{
  "job_id": "test-job-001",
  "job_type": "ai_inference",
  "parameters": {
    "model": "gpt-4",
    "prompt": "Test prompt",
    "max_tokens": 100
  },
  "state": "QUEUED",
  "payment_amount": 100,
  "payment_currency": "AITBC"
}
```

### C. Troubleshooting

**Service Won't Start:**
- Check logs: `sudo journalctl -u [service-name] -f`
- Verify configuration: `sudo systemctl status [service-name]`
- Check port conflicts: `netstat -tulpn`

**Test Times Out:**
- Check service health: `curl http://localhost:[port]/health`
- Verify service dependencies: `sudo systemctl status [service-name]`
- Check for resource exhaustion: `htop`

**Test Fails Intermittently:**
- Review test logs for timing issues
- Increase wait times in tests
- Implement retries for flaky operations
- Check for race conditions

## See Also

- [E2E Test Scenarios](e2e-test-scenarios.md) - Test scenarios and scope
- [E2E Test Execution](e2e-test-execution.md) - Execution, reporting, and maintenance
