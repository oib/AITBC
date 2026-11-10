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
- Round-robin proposer selection over the active validator set in MV-PoA mode
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

The implementation uses **round-robin** selection across the active validator set — the only selection strategy. Stake- and reputation-weighted proposer selection is not implemented.

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

## Validator Set Membership and Proposer Rotation

The validator **set** does not rotate on a schedule. Membership changes only
through explicit registration/deactivation (and slashing); an earlier epoch
rotation mechanism was never invoked and has been removed (#848) rather than
wired in, because its strategies would have demoted validators beyond the top
slots to STANDBY and dropped part of the live set.

The **proposer slot** does rotate — deterministically, per height and round:

- **Round-robin selection**: `select_proposer(height, round)` walks the active
  validator set in sorted-address order, so every node derives the same owner
  for every slot
- **Missed-slot routing** (`consensus_proposer_round_seconds`, default 60s):
  when the scheduled proposer for a height does not produce, the round derived
  from the parent block's timestamp advances and the next validator takes the
  slot — no view-change messages needed

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
ATTESTATION_POST_QUORUM_LINGER_SECONDS=0.0 # extra collection time after quorum; 0 = seal at quorum
# CONSENSUS_VALIDATOR_SET_EPOCH_BLOCKS removed (#848) — validator-set epoch rotation no longer exists
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
- **Multi-validator (this deployment)**: `multi_validator_consensus_enabled=true` with a `VALIDATOR_SET` configured identically on every node. `MultiValidatorPoA` selects proposers round-robin per height and round, and requires `multi_validator_min_attestations` validator attestations on each block. The engine is regression-tested and covered by a 1000-round soak test.
- **PBFT**: `pbft_consensus_enabled=true` runs full pre-prepare / prepare / commit phases before commit. Implemented and tested; **disabled on the live fleet** (`PBFT_CONSENSUS_ENABLED=false`).

## Consensus Flag Matrix and Dormant Paths

Field names in `apps/blockchain-node/src/aitbc_chain/config.py`; the env name is the field name upper-cased (no prefix). Defaults are what a fresh deploy runs. Everything marked **off/unset** is dormant code: it ships on `main` but does nothing until an operator arms it, and arming a consensus-affecting flag is a fleet-wide, one-validator-at-a-time operation (see [Validator Operations](./5_validator.md)).

| Area | Field | Default | Notes |
|---|---|---|---|
| Vote journal | `vote_journal_enabled` | off | Durable per-height vote journal; master for the rows below. |
| Unavailability certificate (UC, #1281) | `vote_journal_justification_enabled` | off | Effective only together with `vote_journal_enabled`. |
| Proposer abandon (#1301) | `vote_journal_abandon_enabled` | off | Effective only together with `vote_journal_enabled`; abandon statements are signed under their own domain. |
| Sealed-rival pull | `vote_journal_sealed_rival_pull` | off | Pull a sealed rival block on contention. |
| Same-hash retry (#1298) | `proposer_same_hash_retry_enabled` | off | Independent of the journal. |
| Round lock (#1242) | `attestation_round_lock_enabled` | off | Re-keys the attestation lock to (height, round). |
| Height lock | `attestation_lock_enabled` | **on** | Legacy height-only lock; already active. |
| Chain-state slashing (#1198) | `consensus_chain_slashing_enabled` | off | Off keeps the legacy node-local persistence of slash-driven deactivation. Armed, deactivation is read from canonical chain state (`VALIDATOR_DEACTIVATE` markers) and local Byzantine detection becomes advisory-only. Fleet-wide arming order is in the `config.py` comment. |
| Mempool reservation (#1300) | `mempool_reservation_enabled` | off | `peek_reserve` drain instead of delete-on-read; database mempool backend only. |
| State transition v24 (#1314) | `state_transition_v24_height` | unset | Height-gated; fleet-wide pin when armed. |
| Empty-state-root refusal (#1325) | `sync_require_state_root_height` | unset | From height H a block with an empty `state_root` is refused on import. `sync_state_root_validation_enabled` is already **on**. |
| Domain separation (#1298) | `consensus_domain_separation_height`, `consensus_legacy_attestation_until_height` | unset | H is a hard cutover to the `aitbc-consensus-v1:*` domains; attestations alone may dual-accept in [H, S). |
| Seal republish | `seal_republish_enabled` | off | Republish an unconfirmed seal. |

Defaults that are not off and not unset, i.e. already live: `attestation_lock_enabled`, `sync_state_root_validation_enabled`, `consensus_enforce_proposer_schedule`, `consensus_require_signed_attest_request`, `proposal_freshness_check_enabled`, `sync_fork_undo_enabled`, `multi_validator_min_attestations` = 2.

### Dormant-path guarantees (and their limits)

- With a flag off, the wiring is pinned by tests rather than assumed: `tests/test_mempool_reservation_off_1300.py` (OFF reservation leaves the marker table empty and moves no counters) and `tests/consensus/test_abandon_off_wiring_1301.py` (OFF abandon starts no listener, subscribes to no `consensus.abandon.*` topic, publishes nothing). Each has an armed control on the same harness.
- `handle_abandon` has no internal flag gate: OFF safety is that the listener is never started. Do not call it from new code paths without checking `abandon_enabled()`.
- Disarming `mempool_reservation_enabled` does not clear markers written while armed. They stay live until released or their TTL (`mempool_reservation_ttl_seconds`, default 120 s) lapses, and until then shield the pool-side deleters; the OFF `drain()` ignores them.
- Arming UC (`vote_journal_enabled` + `vote_journal_justification_enabled`) together on a healthy sandbox mesh stalled the first post-arm height on both test meshes (#1301). UC stays off in production until #1306 / #1311 land and the criteria in #1301 are ratified.

### Flag interactions

Only relationships backed by code or a `config.py` comment are listed.

- **Hard dependencies (enforced in code):** `vote_journal_abandon_enabled` and `vote_journal_justification_enabled` each take effect only with `vote_journal_enabled` also on; the sandbox-tested #1306 nonblocking-persist flag (`unavail_nonblocking_persist_enabled`, once landed) additionally needs the UC barrier.
- **Fleet-uniform height pins:** `state_transition_v24_height`, `consensus_domain_separation_height` and `sync_require_state_root_height` are consensus rules. Arm them at one height on every validator, never mid-history; a mixed set applies different rules and forks (comments in `config.py`). `consensus_legacy_attestation_until_height` only widens the attestation channel inside [H, S); proposals never dual-accept.
- **Backend-scoped:** `mempool_reservation_enabled` is a no-op on the in-memory mempool backend (falls back to `drain()`).
- **Round lock:** `attestation_round_lock_enabled` binds the round into the signed attestation payload and persists (height, round, hash) records, so it changes what attesters sign. Treat it like a pinned rule across the validator set; whether a mixed set interoperates has not been tested.
- **Observed bad combination (sandbox only):** arming `vote_journal_enabled` + `vote_journal_justification_enabled` on all validators at once stalled the first post-arm height on both test meshes (#1301). It has not been tried with a serial, gated arm.
- **Not covered:** the #1311 equivocation-replication flags are not on `main`; their interactions are not documented here until they land.

### Evidence pointers

Sandbox evidence for these paths is indexed on Gitea issue #1301 (evidence-pack index, comment 27500), with the flag-matrix source review in comment 25600, the driver11 replication on a second mesh in comment 27374, and the OFF-wiring tests under #1300 / #1301. The authoritative list of sandboxes and their rules is the AITBC workspace guide (`AGENTS/sandbox.md` in the operator checkout, not in this repository).

## Implementation

The consensus is implemented in:

- `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` - Core PoA logic
- `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` - PBFT protocol
- `apps/blockchain-node/src/aitbc_chain/consensus/slashing.py` - Slashing conditions

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Validator Operations](./5_validator.md) - Validator guide
- [Networking](./6_networking.md) - P2P networking
