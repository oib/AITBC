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
| Coordinator API | 8203 | Job management | Required |
| Blockchain Node | 8202 | Blockchain RPC | Required |
| Wallet Daemon | 8108 | Wallet management | Required |
| GPU Miner | - | Job processing | Required |
| Marketplace | 8102 | Service marketplace | Required |
| Exchange | 8106 | Trading platform | Required |
| Agent Coordinator | 8107 | Agent management | Required |
| PostgreSQL | 5432 | Database | Required |
| Redis | 6379 | Cache | Required |

## Service Orchestration (Systemd)

AITBC uses systemd for service orchestration. Services are managed via systemd unit files.

### Starting Services

```bash
# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# Start Redis
systemctl start redis
systemctl enable redis

# Start AITBC services
systemctl start aitbc-blockchain-node
systemctl start aitbc-coordinator-api
systemctl start aitbc-marketplace
systemctl start aitbc-exchange

# Check service status
systemctl status aitbc-blockchain-node
systemctl status aitbc-coordinator-api
systemctl status aitbc-marketplace
```

### Service Health Checks

```bash
# Check coordinator API
curl -s http://localhost:8203/health

# Check blockchain node
curl -s http://localhost:8080/v1/health

# Check marketplace
curl -s http://localhost:8102/health
```

## Configuration

### Environment Variables

```bash
# Coordinator API
COORDINATOR_URL=http://localhost:8203
CLIENT_API_KEY=test-api-key
ADMIN_API_KEY=test-admin-key

# Blockchain (default RPC port is 8202)
BLOCKCHAIN_URL=http://localhost:8202
BLOCKCHAIN_DATA_DIR=/tmp/blockchain-test

# Wallet
WALLET_DAEMON_URL=http://localhost:8108
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
  "wallet_address": "0x7bf96B6b4b75aF28149Afa237d5C717B3Fe0ED73"
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

- Check logs: `journalctl -u [service-name] -f`
- Verify configuration: `systemctl status [service-name]`
- Check port conflicts: `netstat -tulpn`

**Test Times Out:**

- Check service health: `curl http://localhost:[port]/health`
- Verify service dependencies: `systemctl status [service-name]`
- Check for resource exhaustion: `htop`

**Test Fails Intermittently:**

- Review test logs for timing issues
- Increase wait times in tests
- Implement retries for flaky operations
- Check for race conditions

## Marketplace Escrow Flow Tests

The marketplace escrow E2E test (`tests/e2e/test_marketplace_escrow.py`) exercises a complete offer -> purchase -> escrow lock -> job execution -> release lifecycle. In addition to the variables above, set:

```bash
# Buyer wallet that funds the escrow (must have a real private key)
E2E_BUYER_PRIVATE_KEY=0x...

# Provider/miner wallet that receives the escrow payout
E2E_PROVIDER_PRIVATE_KEY=0x...

# Blockchain node wallet that receives the ESCROW_LOCK funds
E2E_NODE_WALLET_ADDRESS=0x...

# Optional: override the chain_id used in the ESCROW_LOCK transaction
E2E_CHAIN_ID=ait-hub.aitbc.bubuit.net

# Client JWT for coordinator client routes, or a JWT secret to mint one
E2E_CLIENT_TOKEN=eyJ...
# or
JWT_SECRET=at-least-32-characters-long

# Miner authentication: a configured miner API key, an existing miner JWT,
# or a JWT secret to mint a miner JWT
E2E_MINER_API_KEY=miner-api-key-1
# or
E2E_MINER_TOKEN=eyJ...
# or
JWT_SECRET=...
```

When `JWT_SECRET` is used instead of a pre-generated token, the tests mint short-lived access tokens with the buyer address as the client subject and `e2e-test-miner` as the miner subject, so the coordinator must accept tokens signed with the same secret.

## See Also

- [E2E Test Scenarios](e2e-test-scenarios.md) - Test scenarios and scope
- [E2E Test Execution](e2e-test-execution.md) - Execution, reporting, and maintenance
