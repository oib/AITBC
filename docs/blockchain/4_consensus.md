# Consensus Mechanism
Understand AITBC's hybrid Proof-of-Authority/Proof-of-Stake consensus mechanism.

## Overview

AITBC uses a hybrid PoA/PoS consensus mechanism with:
- Fixed block time: 2 seconds
- Multi-validator authority set with role-based permissions
- Stake-weighted proposer selection and validator rotation
- Byzantine fault tolerance via PBFT protocol
- Transaction finality on each block

## Block Production

### Multi-Validator Architecture

AITBC supports multiple validators with distinct roles:
- **PROPOSER**: Authorized to propose new blocks
- **VALIDATOR**: Participates in consensus and validates blocks
- **STANDBY**: Waiting to be promoted to active role

### Proposer Selection

Multiple selection strategies are available:
- **Round-robin**: Validators take turns in fixed order
- **Stake-weighted**: Higher stake increases selection probability
- **Reputation-based**: Performance metrics influence selection
- **Hybrid**: Combines stake and reputation scores (default)

Proposers are selected from active validators with PROPOSER or VALIDATOR roles.

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
5. **Validator Stake**: 1000 AITBC minimum
6. **Fault Tolerance**: Up to 1/3 of validators can be Byzantine (PBFT)

## Validator Requirements

| Requirement | Value |
|-------------|-------|
| Stake | 1000 AITBC minimum |
| Uptime | 99% minimum |
| Latency | < 100ms to peers |
| Reputation | 0.7 threshold (for reputation-based rotation) |

## Byzantine Fault Tolerance (PBFT)

AITBC implements Practical Byzantine Fault Tolerance for safety:
- **Pre-prepare phase**: Proposer broadcasts block proposal
- **Prepare phase**: Validators acknowledge proposal
- **Commit phase**: Validators commit to block execution
- **Execute phase**: Block is finalized and executed

The system tolerates up to 1/3 faulty validators while maintaining safety and liveness.

## Validator Rotation

Validators rotate automatically based on configured strategy:
- **Rotation interval**: Every 100 blocks (configurable)
- **Maximum validators**: 10 (configurable)
- **Strategies**: Round-robin, stake-weighted, reputation-based, or hybrid

Rotation ensures decentralization and prevents single-point failures.

## Network Partition Handling

The consensus mechanism detects and handles network partitions:
- Partitioned validators are marked and excluded from consensus
- Consensus requires majority of active validators (not partitioned)
- 5-second cooldown after partition healing before resuming consensus
- Byzantine behavior detection identifies malicious validators

## Fork Selection

Longest chain rule applies:
- Validators always extend the longest known chain
- Reorgs occur only on conflicting blocks within the last 10 blocks

## Finality

Blocks are considered final after:
- 1 confirmation for normal transactions
- 3 confirmations for high-value transactions

## Configuration

### Environment Variables

```bash
CONSENSUS_MODE=poa                    # Consensus algorithm
PROPOSER_ID=<address>                 # Default proposer (single-validator mode)
ROTATION_INTERVAL=100                 # Blocks between rotations
MAX_VALIDATORS=10                     # Maximum active validators
MIN_STAKE=1000.0                     # Minimum validator stake
REPUTATION_THRESHOLD=0.7              # Minimum reputation for rotation
```

### Single vs Multi-Validator Mode

- **Single-validator**: Use `PROPOSER_ID` for simple setup (genesis wallet only)
- **Multi-validator**: Configure validator set via API or CLI for production

## Implementation

The consensus is implemented in:
- `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` - Core PoA logic
- `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` - PBFT protocol
- `apps/blockchain-node/src/aitbc_chain/consensus/rotation.py` - Validator rotation
- `apps/blockchain-node/src/aitbc_chain/consensus/slashing.py` - Slashing conditions

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Validator Operations](./5_validator.md) - Validator guide
- [Networking](./6_networking.md) - P2P networking
