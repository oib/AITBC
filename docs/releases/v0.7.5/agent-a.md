# v0.7.5 Consensus Activation — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create shared consensus message signing/verification utilities in `aitbc/crypto/`, and shared consensus types that the CLI and other services can consume without depending on `apps/blockchain-node/`.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅, v0.7.3 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/crypto/ aitbc/consensus/ && ./venv/bin/python -m ruff check aitbc/crypto/ aitbc/consensus/ tests/unit/test_consensus_signing.py && ./venv/bin/python -m pytest tests/unit/test_consensus_signing.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/crypto/consensus_signing.py` — `sign_consensus_message()`, `verify_consensus_message()`, `sign_block_hash()` wrappers using secp256k1 | 🔴 P0 | `aitbc/crypto/consensus_signing.py` (new), `aitbc/crypto/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/consensus/` package — shared PBFT message types, validator types, consensus config dataclass | High | `aitbc/consensus/__init__.py` (new), `aitbc/consensus/types.py` (new) | ✅ |
| A3 | Unit tests for A1-A2 | High | `tests/unit/test_consensus_signing.py` (new) | ✅ |

---

## A1: Consensus Signing Utilities

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

---

## A2: Shared Consensus Types

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

---

## A3: Unit Tests

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.5 — Consensus Activation
**Agent**: Agent A (Shared Core)
