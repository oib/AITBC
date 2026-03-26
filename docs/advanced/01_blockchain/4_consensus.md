# Consensus Mechanism
Understand AITBC's proof-of-authority consensus mechanism.

## Overview

AITBC uses a Proof-of-Authority (PoA) consensus mechanism with:
- Fixed block time: 2 seconds
- Authority set of validated proposers
- Transaction finality on each block

## Block Production

### Proposer Selection

Proposers take turns producing blocks in a round-robin fashion. Each proposer gets a fixed time slot.

### Block Structure

```json
{
  "header": {
    "height": 100,
    "timestamp": "2026-02-13T10:00:00Z",
    "proposer": "ait-devnet-proposer-1",
    "parent_hash": "0xabc123...",
    "state_root": "0xdef456...",
    "tx_root": "0xghi789..."
  },
  "transactions": [...],
  "receipts": [...]
}
```

## Consensus Rules

1. **Block Time**: 2 seconds minimum
2. **Block Size**: 1 MB maximum
3. **Transactions**: 500 maximum per block
4. **Fee**: Minimum 0 (configurable)

## Validator Requirements

| Requirement | Value |
|-------------|-------|
| Uptime | 99% minimum |
| Latency | < 100ms to peers |
| Stake | 1000 AITBC |

## Fork Selection

Longest chain rule applies:
- Validators always extend the longest known chain
- Reorgs occur only on conflicting blocks within the last 10 blocks

## Finality

Blocks are considered final after:
- 1 confirmation for normal transactions
- 3 confirmations for high-value transactions

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Validator Operations](./5_validator.md) - Validator guide
- [Networking](./6_networking.md) - P2P networking
