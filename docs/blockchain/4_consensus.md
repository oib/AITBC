# Consensus Mechanism

**Last Updated:** 2026-08-21

Understand AITBC's multi-validator Proof-of-Authority (PoA) consensus mechanism with optional PBFT finality.

> **Current operational model:** The live network runs single-validator PoA by
default. `multi_validator_consensus_enabled` is `False`, so `PoAProposer`
produces every block with the configured `PROPOSER_ID`. The MultiValidatorPoA
engine (round-robin proposer selection, PBFT phases, partition tolerance, and
slashing) is implemented, regression-tested, and now covered by a soak test, but
it is only activated when `multi_validator_consensus_enabled` is explicitly set
to `True`.

## Overview

AITBC uses a multi-validator PoA consensus mechanism with optional PBFT finality:

- Fixed block time: 2 seconds
- Multi-validator authority set with role-based permissions
- Round-robin proposer selection and validator rotation
- Optional Byzantine fault tolerance via PBFT protocol
- Transaction finality on each block

## Block Production

### Multi-Validator Architecture

AITBC supports multiple validators with distinct roles:

- **PROPOSER**: Authorized to propose new blocks
- **VALIDATOR**: Participates in consensus and validates blocks
- **STANDBY**: Waiting to be promoted to active role

### Proposer Selection

The current implementation uses **round-robin** selection across the active validator set. Future rotation strategies may incorporate stake and reputation weighting; they are not active in the default configuration.

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

Finality depends on the consensus mode:

- **Single-validator PoA** (default): finality is probabilistic and relies on the operator-controlled proposer. Downstream consumers such as the cross-chain bridge should use a confirmation-count threshold (`bridge_finality_blocks`) that is at least as strong as the desired security level.
- **Multi-validator PoA + PBFT**: a block that carries a valid PBFT commit certificate (2f+1 commit messages from active validators) is final immediately. The bridge currently derives finality from `bridge_finality_blocks` confirmations; operators should set `bridge_finality_blocks` so that confirmation-count finality is not weaker than the consensus finality guarantee (e.g. 6 confirmations for single-validator PoA, or at least 1 block plus PBFT certificate verification when PBFT is active).

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

- **Single-validator (default)**: Use `PROPOSER_ID` for simple setup (genesis wallet only). The live `PoAProposer` in `poa.py` uses the single `proposer_id` configured for the node, and `multi_validator_consensus_enabled` defaults to `False`. The hub is currently one validator.
- **Multi-validator**: Set `multi_validator_consensus_enabled=True` and configure a validator set via API or CLI for production. The `MultiValidatorPoA` + `PBFTConsensus` engine is implemented and passes a 1000-round soak test, but it is **not wired into live block production** by default.

## Implementation

The consensus is implemented in:

- `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` - Core PoA logic
- `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` - PBFT protocol
- `apps/blockchain-node/src/aitbc_chain/consensus/rotation.py` - Validator rotation
- `apps/blockchain-node/src/aitbc_chain/consensus/slashing.py` - Slashing conditions

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Validator Operations](./5_validator.md) - Validator guide
- [Networking](./6_networking.md) - P2P networking
