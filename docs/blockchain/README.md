# Blockchain Documentation

**Generated**: 2026-03-08 13:06:38
**Last Updated**: 2026-04-22
**Total Files**: 3

## Documentation Files

- [Adding gitea-runner as Third Blockchain Node (aitbc2)](adding_gitea_runner_as_third_node.md) - Complete guide for adding a third node to the AITBC blockchain network, including configuration steps, issues encountered, and verification procedures.
- [Blockchain Synchronization Issues and Fixes](blockchain_synchronization_issues_and_fixes.md) - Documentation of synchronization issues between AITBC nodes and their resolutions.

## Multi-Node Blockchain Workflows

Comprehensive Windsurf workflows for multi-node blockchain deployment and operations:

- **[Core Setup](../../.windsurf/workflows/multi-node-blockchain-setup-core.md)** - Prerequisites, environment configuration, and basic node setup
- **[Operations](../../.windsurf/workflows/multi-node-blockchain-operations.md)** - Daily operations, monitoring, and troubleshooting
- **[Advanced Features](../../.windsurf/workflows/multi-node-blockchain-advanced.md)** - Smart contracts, security testing, and performance optimization
- **[Marketplace Testing](../../.windsurf/workflows/multi-node-blockchain-marketplace.md)** - GPU provider testing, transaction tracking, and verification procedures
- **[Production Deployment](../../.windsurf/workflows/multi-node-blockchain-production.md)** - Security hardening, monitoring, and scaling strategies
- **[Reference](../../.windsurf/workflows/multi-node-blockchain-reference.md)** - Configuration overview, verification commands, and best practices

## Transaction Types

The AITBC blockchain supports the following transaction types:

- **TRANSFER**: Standard value transfer between accounts
- **MESSAGE**: On-chain messaging (value=0, fee-only) - allows sending short text messages without balance transfers
- **RECEIPT_CLAIM**: Claim rewards from job completion receipts
- **GPU_MARKETPLACE**: GPU marketplace transactions (bids, offers, purchases)
- **EXCHANGE**: Exchange transactions (orders, trades, swaps, liquidity)

### MESSAGE Transaction Type

The MESSAGE transaction type allows users to send short on-chain messages without affecting account balances. The message is stored in the transaction payload and only the fee is deducted from the sender's balance.

**Usage:**
```bash
curl -X POST http://localhost:8006/rpc/transaction \
  -H "Content-Type: application/json" \
  -d '{"type":"MESSAGE","from":"address","to":"address","amount":0,"fee":1000,"nonce":1,"payload":{"message":"Hello blockchain!"},"sig":"signature"}'
```

**Characteristics:**
- value must be 0
- fee > 0
- recipient can be any address (or special "null" address)
- No balance transfers (only fee deduction)
- Message stored in transaction payload

## Category Overview
This section contains documentation related to blockchain node setup, synchronization, and network configuration.

---
*Manual index*
