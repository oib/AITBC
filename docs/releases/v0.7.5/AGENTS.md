# v0.7.5 — Agent Task Assignment

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Consensus Activation — Fix all 12 security review findings (6 Critical + 6 High), then activate MultiValidatorPoA + PBFT.

**Goal**: Transform the scaffolding MultiValidatorPoA and PBFT implementations into production-grade consensus, satisfying all gating criteria from the [security review](../v0.7.4/security-review-multivalidator-poa.md), then remove the RuntimeError guards and activate multi-validator consensus.

> **Prerequisites**: [v0.7.4](../v0.7.4/change.log) ✅ (Agent A `feat(v0.7.4-a)`, Agent B pending — but v0.7.5 Agent A only needs v0.7.2/v0.7.3 which are ✅).

> **Risk**: High. Consensus bugs = chain splits. All changes must be tested with multi-node integration tests before activation. Testnet soak test (≥48h) is a mandatory operational requirement before mainnet activation.

> **Not on the critical path**: v0.8.x (trading) and v0.9.0 (atomic settlement) do not depend on v0.7.5. Single-validator PoA remains active until v0.7.5 ships.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (consensus signing utilities, shared types)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (security fixes, consensus activation, tests)

---

## Quick Navigation

### Overview
- [Status Baseline](./overview.md#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](./overview.md#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Consensus Signing Utilities](./agent-a.md#a1-consensus-signing-utilities)
- [Shared Consensus Types](./agent-a.md#a2-shared-consensus-types)
- [Unit Tests](./agent-a.md#a3-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Config](./agent-b.md#b1-config)
- [KeyManager rewrite](./agent-b.md#b2-keymanager-rewrite-to-secp256k1)
- [MultiValidatorPoA fixes](./agent-b.md#b3-multivalidatorpoa-fixes)
- [PBFT fixes](./agent-b.md#b4-pbft-fixes)
- [SlashingManager wiring](./agent-b.md#b5-wire-slashingmanager-into-multivalidatorpoa)
- [ValidatorRotation wiring](./agent-b.md#b6-wire-validatorrotation-into-multivalidatorpoa)
- [Gossip-based PBFT transport](./agent-b.md#b7-gossip-based-pbft-transport)
- [Validator persistence](./agent-b.md#b8-validator-persistence)
- [Metrics](./agent-b.md#b9-metrics)
- [CLI commands](./agent-b.md#b10-cli-commands)
- [Tests](./agent-b.md#b11-tests)
- [Testnet soak test](./agent-b.md#b12-testnet-soak-test)
- [Mainnet activation](./agent-b.md#b13-mainnet-activation)
- [Documentation](./agent-b.md#b14-documentation)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.7.5 Target |
|-----------|----------|---------------|---------------|
| **MultiValidatorPoA** | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (294 lines) | SCAFFOLDING — RuntimeError guard at L45-49, no signature verification, no slashing, no rotation | Fix all 6 findings (C1-C3, C6, H1-H3), remove guard |
| **PBFT** | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (202 lines) | SCAFFOLDING — RuntimeError guard at L60-64, no message signatures, no-op network layer, unsafe view change | Fix all 5 findings (C4-C5, H4-H6), remove guard |
| **SlashingManager** | `apps/blockchain-node/src/aitbc_chain/consensus/slashing.py` (146 lines) | IMPLEMENTED but NOT WIRED — has detect/apply methods, not called from MultiValidatorPoA | Wire into MultiValidatorPoA (C2) |
| **ValidatorRotation** | `apps/blockchain-node/src/aitbc_chain/consensus/rotation.py` (140 lines) | IMPLEMENTED but NOT WIRED — has round-robin/stake/rep/hybrid strategies, not called | Wire into MultiValidatorPoA (C3) |
| **KeyManager** | `apps/blockchain-node/src/aitbc_chain/consensus/keys.py` (173 lines) | WRONG CRYPTO — uses RSA 2048-bit, should use secp256k1 (matching PoA block signatures) | Rewrite to secp256k1 via `eth_keys` |
| **Consensus crypto** | `aitbc/crypto/crypto.py` | EXISTS — `sign_transaction_hash()`, `verify_signature()`, `recover_signer()` use secp256k1 | Add consensus message signing utility (Agent A) |
| **Gossip broker** | `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` | WORKING — `publish()`/`subscribe()` with InMemory + Redis backends, topic-based | Wire PBFT messages to gossip topics (C5) |
| **PoA block signing** | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py:944-999` | WORKING — `_sign_block_hash()` + `verify_block_signature()` via `eth_keys` (secp256k1) | MultiValidatorPoA reuses this pattern |
| **Block model** | `apps/blockchain-node/src/aitbc_chain/base_models.py:25-82` | EXISTS — has `signature`, `proposer`, `state_root`, `parent_hash` fields | No changes needed |
| **BridgeValidator model** | `apps/blockchain-node/src/aitbc_chain/base_models.py:219-239` | EXISTS — validator registration with epoch tracking | Adapt for consensus validator persistence |
| **Config** | `apps/blockchain-node/src/aitbc_chain/config.py` | NO `MULTI_VALIDATOR_CONSENSUS_ENABLED` setting — only env var check in code | Add to ChainSettings |
| **Consensus tests** | `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py` (166 lines) | BASIC — 11 tests for CRUD only, no security/consensus tests | Full test suite: Byzantine, forgery, view change, multi-node |
| **PBFT tests** | — | NONE — only threshold guard tests in `test_v064_multi_chain.py` | Full PBFT test suite |

### Already Implemented (needs wiring, not rewriting)

1. ✅ **SlashingManager** (`slashing.py`) — `detect_double_sign()`, `detect_unavailability()`, `detect_invalid_block()`, `apply_slashing()`, `should_slash()`, `get_slashing_history()` — all implemented, not called from MultiValidatorPoA
2. ✅ **ValidatorRotation** (`rotation.py`) — `should_rotate()`, `rotate_validators()`, 4 strategies (round-robin, stake-weighted, reputation, hybrid) — all implemented, not called
3. ✅ **PoA block signature verification** (`poa.py:969-999`) — `verify_block_signature()` via `eth_keys` secp256k1 — pattern to follow for MultiValidatorPoA
4. ✅ **PoA block creation** (`poa.py:218-518`) — `_compute_block_hash()` (SHA-256 of chain_id|height|parent_hash|timestamp|tx_hashes), `_sign_block_hash()`, state root via Merkle Patricia Trie — pattern to follow
5. ✅ **Gossip broker** (`gossip/broker.py`) — `publish()`/`subscribe()` with topic-based routing, InMemory + Redis backends — ready for PBFT message transport
6. ✅ **Crypto functions** (`aitbc/crypto/crypto.py`) — `sign_transaction_hash()`, `verify_signature()`, `recover_signer()` (secp256k1 via eth_keys/eth_account) — ready for consensus message signing

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/crypto/consensus_signing.py` (new), `aitbc/consensus/` (new types), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 14 items | `apps/blockchain-node/src/aitbc_chain/consensus/`, `apps/blockchain-node/src/aitbc_chain/config.py`, `apps/blockchain-node/src/aitbc_chain/base_models.py`, `apps/blockchain-node/tests/consensus/`, `cli/` |

**Conflict boundary**: Agent A owns `aitbc/crypto/` and `aitbc/consensus/` (new). Agent B owns `apps/blockchain-node/` and `cli/`. Agent B consumes Agent A's consensus signing utilities.

**Sequencing**: Agent A goes first (shared consensus crypto). Agent B starts after Agent A A1 completes (signing utilities needed for C1, C4). Agent B B1 (config) and B2 (keys.py rewrite) can proceed independently in parallel with Agent A.

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.5 — Consensus Activation

---

## Agent A — Shared Core

**Scope**: Create shared consensus message signing/verification utilities in `aitbc/crypto/`, and shared consensus types that the CLI and other services can consume without depending on `apps/blockchain-node/`.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅, v0.7.3 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/crypto/ aitbc/consensus/ && ./venv/bin/python -m ruff check aitbc/crypto/ aitbc/consensus/ tests/unit/test_consensus_signing.py && ./venv/bin/python -m pytest tests/unit/test_consensus_signing.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/crypto/consensus_signing.py` — `sign_consensus_message()`, `verify_consensus_message()`, `sign_block_hash()` wrappers using secp256k1 | 🔴 P0 | `aitbc/crypto/consensus_signing.py` (new), `aitbc/crypto/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/consensus/` package — shared PBFT message types, validator types, consensus config dataclass | High | `aitbc/consensus/__init__.py` (new), `aitbc/consensus/types.py` (new) | ✅ |
| A3 | Unit tests for A1-A2 | High | `tests/unit/test_consensus_signing.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Consensus Signing Utilities

Create `aitbc/crypto/consensus_signing.py`:

```python
def sign_consensus_message(message: dict[str, Any], private_key: str) -> str:
    """Sign a consensus message (PBFT pre-prepare/prepare/commit, vote, etc.).

    Canonical-JSON serializes the message dict, hashes with keccak256,
    and signs with secp256k1 via eth_keys. Returns hex signature.

    This wraps recover_signer()'s signing counterpart — the signature
    can be verified with verify_consensus_message().
    """

def verify_consensus_message(message: dict[str, Any], signature: str, expected_sender: str) -> bool:
    """Verify a consensus message signature.

    Returns True if the signature recovers to expected_sender's address.
    Uses recover_signer() from aitbc/crypto/crypto.py.
    """

def sign_block_hash(block_hash: str, private_key: str) -> str:
    """Sign a block hash with secp256k1 (wraps eth_keys sign_msg_hash).

    This is the shared utility version of PoA's _sign_block_hash().
    MultiValidatorPoA and PBFT use this to sign blocks and block hashes.
    """

def verify_block_signature(block_hash: str, signature: str, expected_proposer: str) -> bool:
    """Verify a block signature (wraps eth_keys recover_public_key_from_msg_hash).

    This is the shared utility version of PoA's verify_block_signature().
    MultiValidatorPoA uses this in validate_block() (C1 fix).
    """
```

Use `eth_keys` directly (matching the pattern in `poa.py:944-999`), not `eth_account` — `eth_keys` is lighter and already used for block signing. The `recover_signer()` function in `crypto.py` uses `keccak256(canonical_json)` which is suitable for PBFT messages; block hashes are already SHA-256 hex strings that can be signed directly as message hashes.

Export from `aitbc/crypto/__init__.py`.

#### A2: Shared Consensus Types

Create `aitbc/consensus/types.py` with shared types that the CLI, governance service, and other services can import without depending on `apps/blockchain-node/`:

```python
class PBFTMessageType(StrEnum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"

@dataclass
class PBFTMessageData:
    """Shared PBFT message type — mirrors apps/blockchain-node's PBFTMessage
    but dependency-free for CLI/SDK consumption."""
    message_type: PBFTMessageType
    sender: str
    view_number: int
    sequence_number: int
    digest: str
    signature: str
    timestamp: float

@dataclass
class ConsensusConfig:
    """Configuration for multi-validator consensus."""
    enabled: bool = False
    fault_tolerance: int = 1
    required_messages: int = 3
    view_change_timeout_seconds: int = 30
    consensus_round_timeout_seconds: int = 10
    validator_set_epoch_blocks: int = 7200  # epoch length

@dataclass
class ValidatorInfo:
    """Shared validator info type for CLI/API consumption."""
    address: str
    stake: float
    reputation: float
    role: str  # "proposer", "validator", "standby"
    is_active: bool
    last_proposed: int = 0
```

Create `aitbc/consensus/__init__.py` exporting these types.

#### A3: Unit Tests

`tests/unit/test_consensus_signing.py` — tests for:
- `sign_consensus_message()` + `verify_consensus_message()` round-trip (valid signature)
- Verification fails with wrong sender
- Verification fails with tampered message
- `sign_block_hash()` + `verify_block_signature()` round-trip
- Block signature verification fails with wrong proposer
- Block signature verification fails with invalid signature format
- PBFTMessageData serialization
- ConsensusConfig defaults

---

## Agent B — Apps & Infrastructure

**Scope**: Fix all 12 security review findings, wire slashing/rotation/keys into MultiValidatorPoA/PBFT, implement gossip-based PBFT transport, add persistence, config, metrics, CLI commands, and comprehensive tests. Remove RuntimeError guards after all fixes are verified.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1 complete (consensus signing utilities). v0.7.3 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/consensus/ apps/blockchain-node/src/aitbc_chain/config.py apps/blockchain-node/src/aitbc_chain/base_models.py cli/aitbc_cli/commands/chain.py
cd /opt/aitbc && PYTHONPATH=apps/blockchain-node/src:aitbc ./venv/bin/python -m pytest apps/blockchain-node/tests/consensus/ -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add `MULTI_VALIDATOR_CONSENSUS_ENABLED` + consensus config to ChainSettings | Medium | `apps/blockchain-node/src/aitbc_chain/config.py` (extend) | ✅ |
| B2 | Rewrite `keys.py` — RSA → secp256k1 via `eth_keys` (use Agent A's `sign_block_hash`/`verify_block_signature`) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/keys.py` (rewrite) | ✅ |
| B3 | **C1**: Add block signature verification to `validate_block()` — verify proposer signature via `verify_block_signature()` | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B4 | **C2 + C6**: Wire `SlashingManager` into MultiValidatorPoA — `record_prepare()` rejects conflicting messages, `detect_byzantine_behavior()` triggers slashing | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B5 | **C3**: Wire `ValidatorRotation` into MultiValidatorPoA — epoch-based rotation, call `should_rotate()`/`rotate_validators()` on block boundaries | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B6 | **C4**: Add PBFT message signatures — sign every message with sender's secp256k1 key, verify on receipt, reject unsigned/invalid | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (extend) | ✅ |
| B7 | **C5**: Implement PBFT network transport via gossip broker — replace `_send_to_validator()` no-op with `gossip.publish()` to PBFT topics | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (extend) | ✅ |
| B8 | **H1**: Replace `attempt_consensus()` stub with real PBFT delegation — pre-prepare → prepare → commit → execute | High | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B9 | **H2 + H3**: Fix `validate_transaction_async()` and `create_block()` — delegate to PoA's state transition + block creation path | High | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B10 | **H4 + H5 + H6**: Fix PBFT fault tolerance (dynamic recalc), safe view change (preserve prepared certificates), view change timeout | High | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (extend) | ✅ |
| B11 | Add consensus state persistence — `ConsensusState` SQLModel for validator set + PBFT state, survive node restart | Medium | `apps/blockchain-node/src/aitbc_chain/base_models.py` (extend), `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B12 | Add consensus metrics — validator count, consensus rounds, view changes, Byzantine detections | Low | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend), `apps/blockchain-node/src/aitbc_chain/observability/` (extend) | ✅ |
| B13 | Add CLI commands — `consensus validators`, `consensus status`, `consensus slashing-history` | Medium | `cli/aitbc_cli/commands/chain.py` (extend) | ✅ |
| B14 | Comprehensive consensus test suite — Byzantine detection + slashing, block forgery rejection, view change safety, network partition recovery, multi-node PBFT integration | 🔴 P0 | `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py` (extend), `apps/blockchain-node/tests/consensus/test_pbft.py` (new), `apps/blockchain-node/tests/consensus/test_consensus_integration.py` (new) | ✅ |

### Agent B — Detailed Instructions

#### B1: Config

Add to `apps/blockchain-node/src/aitbc_chain/config.py` (`ChainSettings` class):
```python
# Multi-validator consensus (v0.7.5)
multi_validator_consensus_enabled: bool = False  # master toggle
consensus_view_change_timeout_seconds: int = 30  # H6 — timeout before view change
consensus_round_timeout_seconds: int = 10  # per-round timeout
consensus_validator_set_epoch_blocks: int = 7200  # C3 — epoch length for rotation
consensus_slashing_enabled: bool = True  # C2 — enable slashing
consensus_slashing_amount: float = 100.0  # stake to slash per offense
consensus_byzantine_threshold: int = 3  # slash count before deactivation
```

Update the RuntimeError guards in `multi_validator_poa.py:45-49` and `pbft.py:60-64` to read from `settings.multi_validator_consensus_enabled` instead of `os.getenv()`. Keep the guard in place until all fixes are verified (B14 passes).

#### B2: Rewrite keys.py

Rewrite `apps/blockchain-node/src/aitbc_chain/consensus/keys.py` to use secp256k1 via `eth_keys` instead of RSA:

- `generate_key_pair()` → generate secp256k1 private key, derive Ethereum address
- `sign_message()` → use `aitbc.crypto.consensus_signing.sign_consensus_message()` (Agent A A1)
- `verify_signature()` → use `aitbc.crypto.consensus_signing.verify_consensus_message()` (Agent A A1)
- Keep the `ValidatorKeyPair` dataclass but change `private_key_pem`/`public_key_pem` to `private_key_hex`/`public_key_hex` (secp256k1 keys are hex, not PEM)
- Keep key persistence (file-based) but update format

This is a **breaking change** for any existing RSA keys — but since MultiValidatorPoA is gated and never activated, no production keys exist.

#### B3: C1 — Block Signature Verification

Extend `multi_validator_poa.py:validate_block()` (lines 98-112):

Current: checks proposer is in validators dict and is active.
Target: also verify the block's cryptographic signature.

```python
def validate_block(self, block: Block, proposer: str) -> bool:
    # Existing checks: proposer in validators, is_active, role
    if not self._check_proposer_membership(proposer):
        return False

    # NEW: Verify block signature (C1)
    if block.signature:
        from aitbc.crypto.consensus_signing import verify_block_signature
        if not verify_block_signature(block.hash, block.signature, proposer):
            return False
    elif self._require_block_signatures:
        # Reject unsigned blocks when signatures are required
        return False

    return True
```

Use Agent A's `verify_block_signature()` from A1. Follow the pattern in `poa.py:969-999` — empty signature is allowed for legacy blocks unless `bridge_block_signature_required` is True.

#### B4: C2 + C6 — Slashing + Conflicting Message Rejection

**C6 fix** — `record_prepare()` (lines 171-188):
- When a conflicting message is detected (same round, different block_hash), **reject it** (return False) instead of recording it and returning True
- Call `detect_byzantine_behavior()` immediately after detecting the conflict
- Trigger slashing via `SlashingManager.apply_slashing()`

**C2 fix** — wire `SlashingManager`:
- Add `self._slashing_manager = SlashingManager()` to `__init__`
- In `detect_byzantine_behavior()`, when Byzantine behavior is detected:
  1. Call `self._slashing_manager.detect_double_sign(validator, block_hash1, block_hash2, height)`
  2. If a SlashingEvent is returned, call `self._slashing_manager.apply_slashing(validator, event)`
  3. `apply_slashing()` sets `validator.is_active = False` and reduces stake
  4. Broadcast a slashing event (via gossip or block metadata)
- Add `get_slashing_history()` method for CLI/API consumption

#### B5: C3 — Validator Rotation

Wire `ValidatorRotation` into MultiValidatorPoA:
- Add `self._rotation = ValidatorRotation(self, rotation_config)` to `__init__`
- Add `maybe_rotate(current_height)` method — called on each block boundary
- If `self._rotation.should_rotate(current_height)`: call `self._rotation.rotate_validators(current_height)`
- Track current epoch: `self._current_epoch = current_height // epoch_blocks`
- On epoch transition: rotate validators per configured strategy, update proposer roles
- Log rotation events

#### B6: C4 — PBFT Message Signatures

Extend `pbft.py`:
- In `pre_prepare_phase()`, `prepare_phase()`, `commit_phase()`: sign each created `PBFTMessage` with the sender's private key using `sign_consensus_message()` from Agent A A1
- Add `_verify_message_signature(message: PBFTMessage) -> bool` method — verifies the signature matches the claimed sender
- In `prepare_phase()` and `commit_phase()`: call `_verify_message_signature()` on incoming messages, reject if invalid
- Store the private key in `PBFTConsensus.__init__()` (passed from config)
- Remove `signature=""` placeholder — all messages must be signed

#### B7: C5 — PBFT Network Transport

Replace `_send_to_validator()` no-op with gossip-based transport:
- Add `self._gossip_backend: GossipBackend | None = None` to `__init__`
- Add `set_gossip_backend(backend: GossipBackend)` method — called during node startup
- `_send_to_validator()`: publish message to gossip topic `f"pbft.{message.message_type.value}.{chain_id}"`
- `_broadcast_message()`: publish to the same topic (gossip broadcasts to all subscribers)
- Add `handle_incoming_message(message: PBFTMessage)` — called when a message is received from the gossip subscription
  - Verify signature (B6)
  - Route to appropriate phase handler based on `message_type`
- In node startup: subscribe to PBFT gossip topics, wire `handle_incoming_message` as the callback

Gossip topic naming:
- `pbft.pre_prepare.{chain_id}`
- `pbft.prepare.{chain_id}`
- `pbft.commit.{chain_id}`
- `pbft.view_change.{chain_id}`

#### B8: H1 — Real Consensus in attempt_consensus()

Replace `attempt_consensus()` (lines 152-169) with real PBFT delegation:
- Create a `PBFTConsensus` instance (if not already created)
- Call `pbft.pre_prepare_phase(proposer, block_hash)` → `prepare_phase()` → `commit_phase()` → `execute_phase()`
- Return True only if all phases complete with quorum
- Handle timeouts: if a phase doesn't complete within `consensus_round_timeout_seconds`, return False (triggers view change via H6)
- Remove the `asyncio.sleep(0.01)` and majority-check stub

#### B9: H2 + H3 — Real Transaction Validation + Block Creation

**H2** — `validate_transaction_async()` (lines 141-150):
- Remove `asyncio.sleep(0.001)` and `hasattr(transaction, "tx_id")` check
- Delegate to the existing PoA transaction validation: call `get_state_transition().apply_transaction()` in a dry-run mode (or call the existing `_validate_transaction_admission()` from `rpc/transactions.py`)
- Check: sender account exists, sufficient balance, valid nonce, valid chain_id

**H3** — `create_block()` (lines 234-242):
- Remove `len(self.validators)` as block height — accept `height` and `parent_hash` parameters
- Compute block hash using the same formula as PoA: `sha256(chain_id|height|parent_hash|timestamp|sorted_tx_hashes)`
- Include parent_hash, transactions, state_root in the block dict
- Sign the block hash with the proposer's private key
- Return a proper Block-compatible dict (not just timestamp hash)

#### B10: H4 + H5 + H6 — PBFT Fault Tolerance, View Change, Timeout

**H4** — dynamic fault tolerance:
- Recalculate `fault_tolerance` and `required_messages` at the start of each consensus round, not just in `__init__`
- `self.fault_tolerance = max(1, len(self.consensus.get_consensus_participants()) // 3)`
- `self.required_messages = 2 * self.fault_tolerance + 1`

**H5** — safe view change:
- `handle_view_change()` must NOT clear `prepared_messages` and `committed_messages` blindly
- Preserve prepared certificates: messages for sequences ≤ `current_sequence` (already committed) are kept
- Only clear messages for sequences > `current_sequence` (uncommitted, need re-proposal)
- Store the prepared certificate for the last committed block to prove it was committed before the view change

**H6** — view change timeout:
- Add `self._consensus_timer: asyncio.Task | None = None`
- Start a timer when a consensus round begins; if it fires before completion, trigger `handle_view_change(current_view + 1)`
- Timer duration: `settings.consensus_view_change_timeout_seconds` (default 30s)
- Cancel the timer when consensus completes successfully
- On view change: restart the timer with an increased timeout (exponential backoff: `timeout * 2^view_change_count`, capped at 5 min)

#### B11: Consensus State Persistence

Add `ConsensusState` SQLModel to `base_models.py`:
```python
class ConsensusState(SQLModel, table=True):
    """Persisted consensus state for MultiValidatorPoA + PBFT."""
    __tablename__ = "consensus_state"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    current_view: int = 0
    current_sequence: int = 0
    current_epoch: int = 0
    validator_set_json: str = ""  # JSON-serialized validator set
    slashing_events_json: str = "[]"  # JSON-serialized slashing history
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Add `save_state()` / `load_state()` methods to `MultiValidatorPoA` using `session_scope()`. Call `save_state()` after each consensus round and on graceful shutdown. Call `load_state()` on node startup.

#### B12: Consensus Metrics

Add Prometheus metrics for consensus:
- `consensus_validators_active` — gauge, active validator count
- `consensus_validators_total` — gauge, total validator count
- `consensus_rounds_total` — counter, consensus rounds attempted
- `consensus_rounds_successful_total` — counter, rounds that reached commit
- `consensus_view_changes_total` — counter, view changes triggered
- `consensus_byzantine_detections_total` — counter, Byzantine validators detected
- `consensus_slashing_events_total` — counter, slashing events applied
- `consensus_round_duration_seconds` — histogram, time per consensus round

Register in `apps/blockchain-node/src/aitbc_chain/observability/`.

#### B13: CLI Commands

Add to `cli/aitbc_cli/commands/chain.py`:
- `aitbc consensus validators` — list active validators (address, stake, reputation, role, last_proposed)
- `aitbc consensus status` — show consensus mode (single/multi), current view, sequence, epoch, fault tolerance
- `aitbc consensus slashing-history` — show slashing events (validator, condition, amount, block height)

These call blockchain-node RPC endpoints that return consensus state.

#### B14: Comprehensive Test Suite

**Extend** `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py`:
- `test_validate_block_rejects_forged_signature` — block with invalid signature is rejected (C1)
- `test_validate_block_accepts_valid_signature` — block with valid signature is accepted (C1)
- `test_record_prepare_rejects_conflicting` — conflicting prepare message returns False (C6)
- `test_byzantine_detection_triggers_slashing` — equivocation → slashing → validator deactivated (C2)
- `test_slashing_reduces_stake` — slashed validator has reduced stake
- `test_slashing_deactivates_after_threshold` — 3 slashing events → is_active=False
- `test_validator_rotation_epoch_transition` — rotation triggers at epoch boundary (C3)
- `test_validator_rotation_round_robin` — round-robin strategy cycles validators
- `test_create_block_includes_parent_hash` — block hash includes parent hash (H3)
- `test_create_block_includes_tx_hashes` — block hash includes transaction hashes (H3)
- `test_validate_transaction_delegates_to_state_transition` — real validation (H2)

**Create** `apps/blockchain-node/tests/consensus/test_pbft.py`:
- `test_pre_prepare_with_signature` — pre-prepare message is signed (C4)
- `test_prepare_with_signature` — prepare message is signed (C4)
- `test_commit_with_signature` — commit message is signed (C4)
- `test_reject_unsigned_message` — unsigned message is rejected (C4)
- `test_reject_forged_signature` — message with wrong sender signature is rejected (C4)
- `test_quorum_reached` — 2f+1 prepare messages → prepared (H4)
- `test_dynamic_fault_tolerance` — adding/removing validators recalculates f (H4)
- `test_view_change_preserves_committed` — committed blocks survive view change (H5)
- `test_view_change_clears_uncommitted` — uncommitted messages are cleared (H5)
- `test_view_change_timeout_triggers` — timeout fires → view change (H6)
- `test_view_change_backoff` — exponential backoff on repeated view changes (H6)
- `test_gossip_transport_publishes` — messages published to gossip topics (C5)
- `test_gossip_transport_receives` — incoming gossip messages handled (C5)

**Create** `apps/blockchain-node/tests/consensus/test_consensus_integration.py`:
- `test_full_consensus_round` — pre-prepare → prepare → commit → execute with 4 validators
- `test_byzantine_validator_slashed` — 1 Byzantine validator equivocates, gets slashed, consensus continues
- `test_block_forgery_rejected` — forged block (invalid signature) rejected by validate_block
- `test_view_change_recovery` — proposer crashes → view change → new proposer → consensus resumes
- `test_network_partition_recovery` — partition heals → consensus resumes
- `test_state_persistence` — save state → restart → load state → consensus continues
- `test_multi_node_pbft` — 3 nodes via InMemoryGossipBackend, 1 Byzantine, consensus reaches commit

---

## Coordination

### Shared Files

Agent A owns `aitbc/crypto/consensus_signing.py` (new) and `aitbc/consensus/` (new). Agent B owns `apps/blockchain-node/` and `cli/`. No file conflicts.

Agent B imports from Agent A's modules:
- `from aitbc.crypto.consensus_signing import sign_consensus_message, verify_consensus_message, sign_block_hash, verify_block_signature`
- `from aitbc.consensus.types import PBFTMessageData, ConsensusConfig, ValidatorInfo`

### Sequencing

1. **Phase 1** (parallel): Agent A A1 (signing utilities), Agent B B1 (config), Agent B B2 (keys.py rewrite)
2. **Phase 2** (Agent A first): Agent A A2 (shared types), Agent B B3 (C1 — needs A1), Agent B B6 (C4 — needs A1)
3. **Phase 3** (Agent B): B4 (C2+C6), B5 (C3), B7 (C5), B9 (H2+H3)
4. **Phase 4** (Agent B): B8 (H1 — needs B6+B7), B10 (H4+H5+H6 — needs B7)
5. **Phase 5** (Agent B): B11 (persistence), B12 (metrics), B13 (CLI)
6. **Phase 6** (parallel): Agent A A3 (unit tests), Agent B B14 (consensus test suite)
7. **Phase 7** (Agent B): Remove RuntimeError guards after B14 passes — activation

### Dependencies

```
v0.7.2 (bridge verification) ✅     v0.7.3 (governance SDK) ✅
    │                                     │
    ├── A1 (signing utils) ──────┐        │
    ├── A2 (shared types) ───────┤        │
    │                             ├── A3 (tests)
    │                             │
    ├── B1 (config) ──────────────┐│
    ├── B2 (keys.py rewrite) ─────┤├── needs A1
    ├── B3 (C1 block sig) ────────┤├── needs A1
    ├── B4 (C2+C6 slashing) ──────┤│
    ├── B5 (C3 rotation) ─────────┤│
    ├── B6 (C4 PBFT sigs) ────────┤├── needs A1
    ├── B7 (C5 gossip) ───────────┤│
    ├── B8 (H1 real consensus) ───┤├── needs B6+B7
    ├── B9 (H2+H3 block/tx) ──────┤│
    ├── B10 (H4+H5+H6 PBFT) ──────┤├── needs B7
    ├── B11 (persistence) ────────┤│
    ├── B12 (metrics) ────────────┤│
    ├── B13 (CLI) ────────────────┤├── needs A2
    └── B14 (tests) ──────────────┘│  needs all
                                  │
    Phase 7: Remove guards ───────┘  needs B14 pass
```

### Activation Gating

The RuntimeError guards at `multi_validator_poa.py:45-49` and `pbft.py:60-64` must remain in place until **all** of the following are met:

- [ ] Agent A A1-A3 complete (signing utilities + tests)
- [ ] Agent B B1-B14 complete (all fixes + tests)
- [ ] All 6 Critical findings fixed and tested (C1-C6)
- [ ] All 6 High findings fixed and tested (H1-H6)
- [ ] All 6 must-test scenarios pass (B14 integration tests)
- [ ] Consensus state persists across restart (B11)
- [ ] Consensus metrics exposed (B12)
- [ ] Code review of all consensus changes
- [ ] Testnet soak test (≥48h, no chain splits) — operational requirement, not code

Only after all checkboxes are met: remove the RuntimeError guards, set `multi_validator_consensus_enabled = true` in config, and deploy to mainnet.

### Rollback Plan

If issues are found post-activation:
1. Set `multi_validator_consensus_enabled = false` in config
2. Restart blockchain-node — RuntimeError guard re-activates, single-validator PoA resumes
3. Investigate and fix issues
4. Re-run testnet soak test before re-activating

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Chain split from consensus bug | Testnet soak test ≥48h before mainnet; rollback plan |
| Slashing false positive | Slashing requires 2+ conflicting messages (cryptographic proof); threshold before deactivation (default 3) |
| View change storm | Exponential backoff on view change timeout (cap 5 min); metrics alert on view_changes_total > 10/min |
| Gossip message flood | Rate limiting on PBFT message handling; ignore messages from non-validators |
| Key compromise | Key rotation via `KeyManager.should_rotate_key()` (default 24h interval); slashing deters key misuse |
| State persistence corruption | `save_state()` is atomic (SQL transaction); `load_state()` validates state hash before applying |
