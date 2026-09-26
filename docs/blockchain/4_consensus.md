# Consensus Mechanism

**Last Updated:** 2026-09-16

Understand AITBC's multi-validator Proof-of-Authority (PoA) consensus mechanism with optional PBFT finality.

> **Current operational model:** Both engines are config-gated. The code
defaults are single-validator PoA (`multi_validator_consensus_enabled=False`,
`pbft_consensus_enabled=False`), where `PoAProposer` produces every block with
the configured `PROPOSER_ID`. **This deployment runs multi-validator PoA**: the
live fleet env sets `MULTI_VALIDATOR_CONSENSUS_ENABLED=true` and
`MULTI_VALIDATOR_MIN_ATTESTATIONS=2`, so `MultiValidatorPoA` does round-robin
proposer selection over the configured `VALIDATOR_SET` and blocks must carry at
least 2 validator attestations. PBFT (`PBFT_CONSENSUS_ENABLED`) is implemented
and regression-tested but **disabled** on the live fleet — enable it only after
a security review and with at least 4 validators (f=1 BFT).

## Overview

AITBC uses a PoA consensus mechanism with an optional multi-validator authority
set and optional PBFT finality:

- Configurable block time via `block_time_seconds` (default: 10 seconds)
- Single proposer (`proposer_id`) by default; multi-validator authority set
  with role-based permissions when `multi_validator_consensus_enabled=true`
- Round-robin proposer selection and validator-set epochs in MV-PoA mode
- Optional Byzantine fault tolerance via the PBFT protocol
  (`pbft_consensus_enabled`, disabled on the live fleet)
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
  "chain_id": "ait-localnet",
  "height": 100,
  "hash": "0xabc123...",
  "parent_hash": "0xdef456...",
  "proposer": "0xDb52...",
  "timestamp": "2026-02-13T10:00:00+00:00",
  "tx_count": 3,
  "state_root": "0xghi789...",
  "bridge_state_root": "0x...",
  "signature": "0x...",
  "transactions": [...]
}
```

## Consensus Rules

1. **Block Time**: `block_time_seconds` (default 10 seconds)
2. **Block Size**: `max_block_size_bytes` (default 1 MB)
3. **Transactions**: `max_txs_per_block` (default 500)
4. **Fee**: `min_fee` (default 0)
5. **Attestation quorum**: `multi_validator_min_attestations` (default 2) when MV-PoA is active
6. **Fault Tolerance**: up to 1/3 of validators can be Byzantine (PBFT, when enabled)

## Validator Requirements

There is no stake-based admission wired into block production. The validator
set is **operator-controlled**: each node's `validator_set` JSON configures the
addresses, roles, and consensus-bookkeeping stake that `MultiValidatorPoA`
uses, and `validator_keys` holds the signing keys this node controls. Neither
moves tokens — the `stake` figure is a weight inside the consensus engine, not
a balance on the chain.

| Requirement | Value |
|-------------|-------|
| Membership | Listed in `validator_set` on every node |
| Signing | Address present in local `validator_keys` (validator-secrets.env) |
| Uptime | High availability expected — missed slots rotate to the next validator |
| Latency | < 100ms to peers recommended |

## Byzantine Fault Tolerance (PBFT)

AITBC implements Practical Byzantine Fault Tolerance for safety:

- **Pre-prepare phase**: Proposer broadcasts block proposal
- **Prepare phase**: Validators acknowledge proposal
- **Commit phase**: Validators commit to block execution
- **Execute phase**: Block is finalized and executed

The system tolerates up to 1/3 faulty validators while maintaining safety and liveness.

## Validator Rotation

In MV-PoA mode the engine rotates the active set on epoch boundaries:

- **Epoch length**: `consensus_validator_set_epoch_blocks` (default 7200 blocks)
- **Strategies implemented** (`consensus/rotation.py`): round-robin,
  stake-weighted, reputation-based, or hybrid — over the `validator_set`
  weights, not on-chain balances
- **Missed-slot routing** (`consensus_proposer_round_seconds`, default 60s):
  when the scheduled proposer for a height does not produce, the round derived
  from the parent block's timestamp advances and the next validator takes the
  slot — no view-change messages needed

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
# Block production
PROPOSER_ID=<0x address>                  # block-signing identity (must match keystore)
ENABLE_BLOCK_PRODUCTION=true              # hub/proposer; false on followers
BLOCK_PRODUCTION_CHAINS=                  # chains to produce for (empty = all supported)
BLOCK_TIME_SECONDS=10                     # block interval

# Multi-validator PoA (config-gated; live fleet: MULTI_VALIDATOR_CONSENSUS_ENABLED=true)
MULTI_VALIDATOR_CONSENSUS_ENABLED=true
VALIDATOR_SET='[{"address":"0x...","stake":"1000"}, ...]'   # JSON, same on all nodes
VALIDATOR_KEYS='{"0x<address>":"<private key>"}'            # in validator-secrets.env
MULTI_VALIDATOR_MIN_ATTESTATIONS=2        # attestation quorum on MV-PoA blocks
MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS=1.0
CONSENSUS_VALIDATOR_SET_EPOCH_BLOCKS=7200 # epoch length for validator-set rotation
CONSENSUS_ENFORCE_PROPOSER_SCHEDULE=true  # drop pre-prepares from off-schedule proposers

# PBFT (implemented, disabled on the live fleet)
PBFT_CONSENSUS_ENABLED=false
PBFT_REQUIRE_SIGNATURES=true
PBFT_VIEW_CHANGE_TIMEOUT=30
CONSENSUS_VIEW_CHANGE_TIMEOUT_SECONDS=30
CONSENSUS_ROUND_TIMEOUT_SECONDS=10
```

### Single vs Multi-Validator Mode

- **Single-validator (code default)**: `multi_validator_consensus_enabled=False`. `PoAProposer` in `poa.py` produces every block with the configured `proposer_id` — a simple setup where the hub is the only validator.
- **Multi-validator (this deployment)**: `multi_validator_consensus_enabled=true` with a `VALIDATOR_SET` configured identically on every node. `MultiValidatorPoA` selects proposers round-robin per epoch and requires `multi_validator_min_attestations` validator attestations on each block. The engine is regression-tested and covered by a 1000-round soak test.
- **PBFT**: `pbft_consensus_enabled=true` runs full pre-prepare / prepare / commit phases before commit. Implemented and tested; **disabled on the live fleet** (`PBFT_CONSENSUS_ENABLED=false`).

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
