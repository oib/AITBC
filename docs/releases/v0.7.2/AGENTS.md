# v0.7.2 — Agent Task Assignment

**Release Theme**: Bridge Verification — In-Process Cryptographic Proof Verification, Block Header Verification, Validator Set Tracking, Oracle Client Stub

**Goal**: Replace the current trivially forgeable bridge proof validation (`_validate_proof` in `cross_chain/bridge.py:399-475`, which only checks field equality + signature format) with cryptographic Merkle proof verification using the existing `merkle_patricia_trie.verify_proof()`. Verify block header proposer signatures against the v0.7.1 validator set registry. Track block finality per chain. Include an abstract oracle client interface for future external oracle integration.

> **Rescope from original change.log**: The original v0.7.2 plan assumed external oracle infrastructure (`oracle1.aitbc.bubuit.net`, `oracle2.aitbc.bubuit.net`) that **does not exist**. No oracle client code, light client library, or deployed oracle network are present. v0.7.2 is rescoped to use **in-process cryptographic verification** with existing Merkle Patricia Trie infrastructure (`merkle_patricia_trie.verify_proof`). External oracle integration is deferred to v0.8.x or v0.9.x. A stub oracle client interface is included to allow future integration without breaking changes.

> **Hard prerequisite**: v0.7.1 must be **complete and committed** before v0.7.2 implementation starts. v0.7.2's core verification depends on:
> - v0.7.1 Agent A: `ValidatorSetRegistry`, `verify_threshold_signatures`, `ValidatorSet`/`ValidatorInfo` types (✅ committed `1fcf1e829`)
> - v0.7.1 Agent B: `BridgeValidator` SQLModel table, block header `signature` field, `_verify_threshold_signatures` in bridge.py, validator RPC endpoints (🔴 NOT STARTED — v0.7.0 Agent B is still uncommitted)
>
> **Do NOT start v0.7.2 implementation until v0.7.1 Agent B is complete.** This AGENTS.md is a planning document only.

> **Scope constraint**: This release **unfences** the bridge release path. `BRIDGE_RELEASE_ENABLED=false` (config.py:290) is flipped to `true` after Merkle proof verification is operational and tested. This is the single most security-critical change in the v0.7.x series — the fence has been in place since v0.5.16 to prevent unauthorized minting.

> **No external security audit**: All development is in-house. Internal code review + comprehensive test coverage replaces the external audit gate (same as v0.7.1).

> **Risk**: High. This release unfences the bridge release path. The Merkle proof verification must be correct — a bug here means an attacker can mint tokens on the destination chain without a real lock on the source chain. The existing `merkle_patricia_trie.verify_proof` is tested but has not been used in the bridge path before.

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅ (Agent A committed), [v0.7.1](../v0.7.1/change.log) (Agent A ✅ committed, Agent B 🔴 not started), [v0.5.16](../v0.5.16/change.log) ✅ (bridge proof hardening + release fence).

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.7.2 Target |
|-----------|----------|---------------|---------------|
| **Merkle Patricia Trie** | `state/merkle_patricia_trie.py:73-121` | ✅ Complete — `verify_proof(key, value, proof)` + `get_proof(key)` + `get_root()` | Use in bridge `_validate_proof` to verify lock event inclusion against source chain state root |
| **State root computation** | `state/merkle_patricia_trie.py:402-419` | ✅ Complete — `StateManager.compute_state_root(accounts)` | No change — used to compute/verify state roots |
| **State root utils** | `state/state_root_utils.py:17-34` | ✅ Complete — `compute_state_root_full()`, `compute_state_root_incremental()` | No change — bridge uses these to get source chain state root |
| **Bridge proof validation** | `cross_chain/bridge.py:399-475` | ⚠️ PARTIAL — field equality + proposer sig format + block anchor + chain_id. No Merkle proof, no proposer-set membership. | Replace with Merkle proof verification against state root + block header signature verification + finality check |
| **Proposer signature verification** | `cross_chain/bridge.py:477-523` | ⚠️ Accepts ANY valid secp256k1 signer (comment lines 514-517). | v0.7.1 replaces with threshold sig verification. v0.7.2 adds Merkle proof on top. |
| **Block header model** | `base_models.py:25-76` | ⚠️ NO SIGNATURE — `proposer: str` is address only, `state_root: str \| None` exists. No `signature` field. | v0.7.1 B3 adds `signature: str = ""`. v0.7.2 uses it for block header verification. |
| **Remote chain block header storage** | — | ❌ NONE — `Block` table only stores local chain blocks. No `BridgeBlockHeader` or equivalent. | Create `BridgeBlockHeader` SQLModel table: chain_id, height, hash, proposer, state_root, signature, timestamp, finality_confirmed |
| **Finality tracking** | — | ❌ NONE — no confirmation counting, no finality threshold config. | Add finality tracking: count confirmations per chain, configurable threshold, reject non-finalized for large transfers |
| **Finality config** | `config.py` | ❌ NONE — no `bridge_verification_mode`, `bridge_min_confirmations`, `bridge_finality_blocks`, `bridge_large_transfer_threshold`. | Add all four config fields with env var defaults |
| **Validator set tracking (DB)** | — | ❌ NONE — v0.7.1 Agent A has in-memory `ValidatorSetRegistry`, but no SQLModel persistence. | v0.7.1 Agent B creates `BridgeValidator` table. v0.7.2 adds epoch tracking + grace period logic. |
| **Oracle client** | — | ❌ NONE — no abstract interface, no in-process verifier, no external stub. | Create `OracleClient` ABC + `InProcessVerifier` + `ExternalOracleClient` stub |
| **Bridge release fence** | `config.py:290`, `rpc/bridge.py:105` | ✅ EXISTS — `bridge_release_enabled: bool = False` gates confirm/batch_confirm | **UNFENCE** after Merkle proof verification is operational + tested. Flip default to `true`. |
| **Shared bridge SDK** | `aitbc/bridge/` (6 files) | ✅ EXISTS — BridgeClient, types, proof, multisig, validators (v0.7.0 + v0.7.1 Agent A) | Extend with oracle.py, verification.py, finality types |
| **CLI bridge commands** | `cli/aitbc_cli/commands/bridge.py` | ✅ 9 commands exist (v0.7.0 Agent B) + 2 security commands (v0.7.1 Agent B) | Add `oracle-status` command |
| **Threat model** | `docs/architecture/bridge-threat-model.md` | ⚠️ v0.7.1 B1 creates this. If v0.7.1 Agent B hasn't completed, this is missing. | Extend with v0.7.2-specific threats (Merkle proof forgery, finality bypass, state root manipulation) |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Merkle Patricia Trie** — `verify_proof(key, value, proof)`, `get_proof(key)`, `get_root()` all implemented and tested
2. ✅ **State root computation** — `StateManager.compute_state_root()` + `compute_state_root_full/incremental` utilities
3. ✅ **Block model has `state_root` field** — `Block.state_root: str | None` at line 41
4. ✅ **Bridge release fence active** — `BRIDGE_RELEASE_ENABLED=false` prevents unauthorized minting
5. ✅ **Shared bridge SDK** — BridgeClient, types, proof utilities, multisig, validators (v0.7.0 + v0.7.1 Agent A)
6. ✅ **v0.7.1 Agent A committed** — ValidatorSetRegistry, verify_threshold_signatures, ValidatorSet/ValidatorInfo types

### Hard Blockers (must be resolved before v0.7.2 implementation)

1. 🔴 **v0.7.1 Agent B not started** — Need: `BridgeValidator` SQLModel table, block header `signature` field, `_verify_threshold_signatures` in bridge.py, validator RPC endpoints
2. 🔴 **v0.7.0 Agent B uncommitted** — All v0.7.0 Agent B work (RPC endpoints, CLI, monitoring, tests) is in the working tree but not committed
3. 🔴 **No remote chain block header storage** — Must create `BridgeBlockHeader` table before Merkle proof verification can work (need to store source chain block headers with state roots)
4. 🔴 **Threat model may not exist** — v0.7.1 B1 creates `docs/architecture/bridge-threat-model.md`; if v0.7.1 Agent B hasn't completed, this is missing

### Architecture: Bridge Verification (v0.7.2)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/bridge/ — EXTEND + NEW MODULES)                   │
│                                                                      │
│  Verification types (A1 — EXTEND types.py):                          │
│    BridgeBlockHeader — remote chain block header dataclass           │
│    FinalityConfig — finality threshold config dataclass              │
│    ProofVerificationResult — result of proof verification            │
│                                                                      │
│  Oracle client interface (A2 — NEW oracle.py):                       │
│    OracleClient ABC — abstract verification interface                │
│    InProcessVerifier — default, calls MerkleProofVerifier protocol   │
│    ExternalOracleClient — stub for future external oracle            │
│    VerificationMode enum — "in_process" | "oracle"                   │
│                                                                      │
│  Verification utilities (A3 — NEW verification.py):                  │
│    validate_block_header(header, validator_set) — sig check          │
│    check_finality(header, confirmations, config) — threshold check   │
│    build_verification_message(header) — canonical msg for sig        │
│                                                                      │
│  BridgeClient extensions (A4):                                       │
│    get_block_header(chain_id, height) — RPC method                   │
│    oracle_status() — RPC method                                      │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Blockchain Node                      │
│                         │    │ (apps/blockchain-node/)              │
│  bridge oracle-status   │    │                                      │
│  Uses BridgeClient (A4) │    │  Remote block header storage (B2):   │
│                         │    │    BridgeBlockHeader SQLModel (NEW)  │
│                         │    │    fields: chain_id, height, hash,   │
│                         │    │    proposer, state_root, signature,  │
│                         │    │    timestamp, finality_confirmed     │
│                         │    │                                      │
│                         │    │  Merkle proof verification (B3):     │
│                         │    │    _validate_proof → use             │
│                         │    │    merkle_patricia_trie.verify_proof │
│                         │    │    against stored state_root         │
│                         │    │                                      │
│                         │    │  Block header verification (B4):     │
│                         │    │    Verify proposer signature on      │
│                         │    │    source chain block header         │
│                         │    │    using v0.7.1 validator set        │
│                         │    │                                      │
│                         │    │  Finality tracking (B5):             │
│                         │    │    Track confirmations per chain     │
│                         │    │    Reject non-finalized for large    │
│                         │    │    transfers                         │
│                         │    │                                      │
│                         │    │  Validator set epoch tracking (B6):  │
│                         │    │    DB-backed epoch history           │
│                         │    │    Grace period for in-flight xfers  │
│                         │    │    Reject stale validator sets       │
│                         │    │                                      │
│                         │    │  Unfence release path (B7):          │
│                         │    │    BRIDGE_RELEASE_ENABLED → true     │
│                         │    │    After all verification is tested  │
│                         │    │                                      │
│                         │    │  Config (B1):                        │
│                         │    │    bridge_verification_mode          │
│                         │    │    bridge_min_confirmations          │
│                         │    │    bridge_finality_blocks            │
│                         │    │    bridge_large_transfer_threshold   │
│                         │    │                                      │
│                         │    │  Tests (B8):                         │
│                         │    │    Merkle proof, finality,           │
│                         │    │    block header, validator epoch     │
└─────────────────────────┘    └──────────────────────────────────────┘

Phase 0 (prerequisite — Agent B):
  v0.7.1 Agent B must be complete (BridgeValidator table, block header
  signature field, threshold sig verification in bridge.py)
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/bridge/types.py` (extend), `aitbc/bridge/oracle.py` (new), `aitbc/bridge/verification.py` (new), `aitbc/bridge/__init__.py` (extend), `aitbc/bridge/client.py` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `aitbc/constants.py`, `apps/blockchain-node/src/aitbc_chain/config.py`, `base_models.py`, `cross_chain/bridge.py`, `rpc/bridge.py`, `rpc/router.py`, `cli/aitbc_cli/commands/bridge.py`, `apps/blockchain-node/tests/` |

**Conflict boundary**: Agent A owns `aitbc/bridge/` package. Agent B owns all `apps/`, `cli/`, and `aitbc/constants.py`. Agent B consumes Agent A's `OracleClient`, `InProcessVerifier`, verification types, and `BridgeClient` extensions. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK — oracle interface, types, verification utilities). Agent B starts after Agent A completes A1-A3 (B3 Merkle proof verification depends on A1 types + A3 utilities). B1 (config), B2 (block header table) can proceed in parallel with Agent A.

**Hard dependency**: v0.7.1 Agent B must be complete before either agent starts v0.7.2 implementation.

---

## Agent A — Shared Core

**Scope**: Extend the bridge SDK with oracle client interface, verification types, and block header/finality validation utilities. These are dependency-free shared types that Agent B's blockchain node implementation consumes.

**Working directory**: `/opt/aitbc/aitbc/bridge/`

**Prerequisite**: v0.7.1 Agent A ✅ (committed `1fcf1e829`). v0.7.1 Agent B ✅ (committed `a4ea61295` — provides `BridgeValidator` table + block header `signature` field that the types mirror).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ && ./venv/bin/python -m ruff check aitbc/bridge/ tests/unit/test_bridge_verification.py && ./venv/bin/python -m pytest tests/unit/test_bridge_verification.py tests/unit/test_bridge_security.py tests/unit/test_bridge_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Extend bridge types — BridgeBlockHeader, FinalityConfig, ProofVerificationResult, VerificationMode enum | 🔴 P0 | `aitbc/bridge/types.py` (extend), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/bridge/oracle.py` — OracleClient ABC, InProcessVerifier, ExternalOracleClient stub | 🔴 P0 | `aitbc/bridge/oracle.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A3 | Create `aitbc/bridge/verification.py` — block header validation, finality check, verification message builder | 🔴 P0 | `aitbc/bridge/verification.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A4 | Extend BridgeClient with block header + oracle status RPC methods + unit tests for A1-A3 | High | `aitbc/bridge/client.py` (extend), `tests/unit/test_bridge_verification.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Extend Bridge Types

Extend `aitbc/bridge/types.py` with verification-related types.

**New dataclasses**:

```python
class VerificationMode(StrEnum):
    """Bridge proof verification mode."""
    IN_PROCESS = "in_process"  # default — use local Merkle trie
    ORACLE = "oracle"          # future — external oracle (stub only in v0.7.2)


@dataclass
class BridgeBlockHeader:
    """A block header from a remote (source) chain.

    Used to anchor bridge proofs — the Merkle proof is verified against
    ``state_root``, and the block header's proposer signature is verified
    against the validator set (v0.7.1).
    """
    chain_id: str
    height: int
    hash: str
    parent_hash: str
    proposer: str               # proposer address
    state_root: str             # state root at this block
    signature: str = ""         # proposer signature (v0.7.1 field)
    timestamp: datetime | None = None
    finality_confirmed: bool = False  # set when finality threshold met
    confirmation_count: int = 0       # number of confirmations seen


@dataclass
class FinalityConfig:
    """Configuration for block finality tracking."""
    min_confirmations: int = 3          # minimum confirmations for any transfer
    finality_blocks: int = 6            # full finality threshold
    large_transfer_threshold: int = 10000  # transfers above this require full finality
    grace_period_seconds: int = 3600    # validator set transition grace period


@dataclass
class ProofVerificationResult:
    """Result of a bridge proof verification attempt."""
    valid: bool
    error: str = ""
    block_height: int = 0
    state_root: str = ""
    finality_confirmed: bool = False
    validator_epoch: int = 0
    verification_mode: VerificationMode = VerificationMode.IN_PROCESS
```

Update `aitbc/bridge/__init__.py` to re-export `BridgeBlockHeader`, `FinalityConfig`, `ProofVerificationResult`, `VerificationMode`.

#### A2: Oracle Client Interface

Create `aitbc/bridge/oracle.py` — abstract oracle client interface with in-process default and external stub.

```python
"""Bridge oracle client interface (v0.7.2 §A2).

Abstract interface for bridge proof verification. The default
implementation (InProcessVerifier) uses local cryptographic verification
(Merkle proofs + block header signatures). A stub ExternalOracleClient
is included for future external oracle integration (deferred to v0.8.x+).

The InProcessVerifier delegates Merkle proof verification to a callable
provided by the blockchain node (which has access to the Merkle Patricia
Trie). This keeps the shared SDK dependency-free — the actual trie
verification happens in apps/blockchain-node/.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Protocol

from .types import (
    BridgeBlockHeader,
    FinalityConfig,
    ProofVerificationResult,
    VerificationMode,
)

logger = logging.getLogger(__name__)


class MerkleProofVerifier(Protocol):
    """Protocol for Merkle proof verification (implemented by blockchain node)."""

    def verify_merkle_proof(
        self,
        state_root: str,
        key: str,
        value: str,
        proof: list[bytes],
    ) -> bool:
        """Verify a Merkle proof against a state root."""
        ...


class OracleClient(ABC):
    """Abstract base class for bridge proof verification oracles."""

    @abstractmethod
    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof against a block header."""
        ...

    @abstractmethod
    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check if a block header has sufficient finality for a transfer."""
        ...

    @property
    @abstractmethod
    def mode(self) -> VerificationMode:
        """The verification mode of this oracle."""
        ...


class InProcessVerifier(OracleClient):
    """Default in-process verification using local cryptographic primitives.

    Delegates Merkle proof verification to a MerkleProofVerifier callable
    provided by the blockchain node. Block header signature verification
    uses aitbc.bridge.multisig utilities.
    """

    def __init__(
        self,
        merkle_verifier: MerkleProofVerifier | None = None,
    ) -> None:
        self._merkle_verifier = merkle_verifier

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.IN_PROCESS

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof in-process."""
        # 1. Verify block header state root matches proof
        # 2. Verify Merkle proof (if merkle_verifier is set)
        # 3. Check finality
        # 4. Return result
        ...

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check finality — large transfers require full finality."""
        threshold = (
            finality_config.finality_blocks
            if transfer_amount >= finality_config.large_transfer_threshold
            else finality_config.min_confirmations
        )
        return block_header.confirmation_count >= threshold


class ExternalOracleClient(OracleClient):
    """Stub for future external oracle integration.

    NOT IMPLEMENTED in v0.7.2. Raises NotImplementedError if used.
    External oracle integration is deferred to v0.8.x or v0.9.x when
    oracle infrastructure is actually deployed.
    """

    def __init__(self, endpoint: str = "") -> None:
        self._endpoint = endpoint
        logger.warning("ExternalOracleClient is a stub — not implemented in v0.7.2")

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.ORACLE

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        raise NotImplementedError("External oracle integration deferred to v0.8.x+")

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        raise NotImplementedError("External oracle integration deferred to v0.8.x+")
```

#### A3: Verification Utilities

Create `aitbc/bridge/verification.py` — block header validation and finality checking utilities.

```python
"""Bridge verification utilities (v0.7.2 §A3).

Block header signature validation and finality threshold checking.
These utilities are used by the InProcessVerifier and by the blockchain
node's bridge proof verification path.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import BridgeBlockHeader, FinalityConfig, ValidatorSet

logger = logging.getLogger(__name__)


def build_verification_message(header: BridgeBlockHeader) -> dict[str, Any]:
    """Build the canonical message dict that a block header proposer signs.

    This is the block header without the signature field. Key ordering
    does not matter — recover_signer re-serializes with sort_keys=True.
    """
    return {
        "chain_id": header.chain_id,
        "height": header.height,
        "hash": header.hash,
        "parent_hash": header.parent_hash,
        "proposer": header.proposer,
        "state_root": header.state_root,
    }


def validate_block_header(
    header: BridgeBlockHeader,
    validator_set: ValidatorSet | None = None,
) -> tuple[bool, str, str | None]:
    """Validate a block header's proposer signature.

    Args:
        header: The block header to validate.
        validator_set: Optional validator set for membership check.
            If provided, the recovered signer must be a member.

    Returns:
        (valid, error_message, recovered_address)
    """
    if not header.signature:
        return False, "Block header has no signature", None

    message_data = build_verification_message(header)
    recovered = recover_signer(message_data, header.signature)
    if recovered is None:
        return False, "Invalid block header signature", None

    if validator_set is not None:
        if recovered not in validator_set.addresses:
            return False, f"Signer {recovered} not in validator set", recovered

    return True, "", recovered


def check_finality(
    header: BridgeBlockHeader,
    config: FinalityConfig,
    transfer_amount: int,
) -> tuple[bool, int]:
    """Check if a block header has sufficient finality for a transfer.

    Large transfers (>= config.large_transfer_threshold) require full
    finality (config.finality_blocks confirmations). Small transfers
    require only config.min_confirmations.

    Returns:
        (has_finality, required_confirmations)
    """
    required = (
        config.finality_blocks
        if transfer_amount >= config.large_transfer_threshold
        else config.min_confirmations
    )
    return header.confirmation_count >= required, required
```

#### A4: BridgeClient Extensions + Unit Tests

Extend `aitbc/bridge/client.py` with block header and oracle status RPC methods:

```python
async def get_block_header(self, chain_id: str, height: int) -> dict[str, Any]:
    """Get a remote chain block header."""
    resp = await self._ensure_client().get(f"/bridge/block-headers/{chain_id}/{height}")
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())

async def oracle_status(self) -> dict[str, Any]:
    """Get bridge oracle/verification status."""
    resp = await self._ensure_client().get("/bridge/oracle/status")
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())
```

**`tests/unit/test_bridge_verification.py`** — unit tests for A1-A4:
- `test_bridge_block_header_dataclass` — all fields
- `test_bridge_block_header_defaults` — signature="", finality_confirmed=False
- `test_finality_config_defaults` — min_confirmations=3, finality_blocks=6, etc.
- `test_proof_verification_result_defaults` — valid=False, verification_mode=IN_PROCESS
- `test_verification_mode_enum` — IN_PROCESS, ORACLE values
- `test_in_process_verifier_mode` — returns IN_PROCESS
- `test_in_process_verifier_check_finality_small_transfer` — min_confirmations threshold
- `test_in_process_verifier_check_finality_large_transfer` — finality_blocks threshold
- `test_external_oracle_client_stub_raises` — NotImplementedError on verify_proof
- `test_external_oracle_client_mode` — returns ORACLE
- `test_oracle_client_is_abstract` — cannot instantiate OracleClient directly
- `test_build_verification_message` — correct fields, no signature
- `test_validate_block_header_valid` — valid sig, no validator set
- `test_validate_block_header_with_validator_set` — valid sig + member
- `test_validate_block_header_non_member` — valid sig but not in set
- `test_validate_block_header_no_signature` — empty signature rejected
- `test_validate_block_header_invalid_signature` — recover_signer returns None
- `test_check_finality_meets_threshold` — enough confirmations
- `test_check_finality_below_threshold` — insufficient confirmations
- `test_check_finality_large_transfer_requires_more` — large transfer needs finality_blocks
- `test_bridge_client_get_block_header` — mocked RPC
- `test_bridge_client_oracle_status` — mocked RPC
- `test_package_reexport_verification` — new names exported from aitbc.bridge

---

## Agent B — Apps & Infrastructure

**Scope**: Add bridge verification config, create remote block header storage, replace field-equality proof validation with Merkle proof verification, implement block header signature verification, finality tracking, validator set epoch tracking, unfence release path, add CLI command, write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/` and `/opt/aitbc/cli/`

**Prerequisite**: v0.7.1 Agent B must be complete (BridgeValidator table, block header signature field, threshold sig verification). v0.7.0 Agent B must be committed.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/config.py apps/blockchain-node/src/aitbc_chain/base_models.py apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py apps/blockchain-node/src/aitbc_chain/rpc/bridge.py apps/blockchain-node/src/aitbc_chain/rpc/router.py cli/aitbc_cli/commands/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v072_bridge_verification.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add bridge verification config fields + constants | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `aitbc/constants.py` | ⬜ |
| B2 | Create BridgeBlockHeader SQLModel table for remote chain headers | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py` (or new models file) | ⬜ |
| B3 | Replace `_validate_proof` with Merkle proof verification | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B4 | Implement block header signature verification using v0.7.1 validator set | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B5 | Implement finality tracking — confirmations per chain, threshold enforcement | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B6 | Validator set epoch tracking with DB persistence + grace period | High | `apps/blockchain-node/src/aitbc_chain/base_models.py`, `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B7 | Unfence bridge release path + add CLI `oracle-status` command | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `cli/aitbc_cli/commands/bridge.py` | ⬜ |
| B8 | Integration tests + verify mypy/ruff/pytest clean | High | `apps/blockchain-node/tests/test_v072_bridge_verification.py` (new) | ⬜ |

### Agent B — Detailed Instructions

#### B1: Bridge Verification Config + Constants

In `aitbc/constants.py`, add:
```python
# Bridge verification config (v0.7.2)
BRIDGE_VERIFICATION_MODE = "in_process"       # "in_process" | "oracle"
BRIDGE_MIN_CONFIRMATIONS = 3                   # minimum confirmations for any transfer
BRIDGE_FINALITY_BLOCKS = 6                     # full finality threshold
BRIDGE_VALIDATOR_SET_GRACE_PERIOD = 3600       # seconds for validator set transition
BRIDGE_LARGE_TRANSFER_THRESHOLD = 10000        # transfers above this require full finality
```

In `apps/blockchain-node/src/aitbc_chain/config.py`, add to Settings:
```python
bridge_verification_mode: str = "in_process"
bridge_min_confirmations: int = 3
bridge_finality_blocks: int = 6
bridge_validator_set_grace_period: int = 3600
bridge_large_transfer_threshold: int = 10000
```

#### B2: Remote Block Header Storage

Create `BridgeBlockHeader` SQLModel table in `base_models.py` (or a new `bridge_models.py`):

```python
class BridgeBlockHeader(SQLModel, table=True):
    """Block header from a remote (source) chain — used for bridge proof verification."""
    __tablename__ = "bridge_block_header"
    __table_args__ = (
        UniqueConstraint("chain_id", "height", name="uix_bridge_block_chain_height"),
        Index("idx_bridge_block_chain_finality", "chain_id", "finality_confirmed"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    height: int = Field(index=True)
    hash: str = Field(index=True)
    parent_hash: str
    proposer: str
    state_root: str
    signature: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finality_confirmed: bool = False
    confirmation_count: int = 0
```

Add Alembic migration under `apps/blockchain-node/alembic/versions/` using `if_not_exists=True`.

#### B3: Merkle Proof Verification

Replace `_validate_proof` in `cross_chain/bridge.py` (lines 399-475) with:

1. **Field validation** (keep existing field equality checks)
2. **Block header lookup** — fetch `BridgeBlockHeader` from DB by `chain_id` + `block_height`
3. **State root verification** — verify `proof.state_root` matches `block_header.state_root`
4. **Merkle proof verification** — use `merkle_patricia_trie.verify_proof(key, value, proof)` against the block header's state root. The proof must include the lock event in the state trie.
5. **Block header signature verification** — use `aitbc.bridge.verification.validate_block_header()` with the v0.7.1 validator set
6. **Finality check** — use `aitbc.bridge.verification.check_finality()` with the transfer amount

Wire the `InProcessVerifier` from A2 as the verification backend, passing the blockchain node's `MerklePatriciaTrie` as the `MerkleProofVerifier`.

#### B4: Block Header Signature Verification

Use `validate_block_header()` from A3 to verify the block header's proposer signature against the v0.7.1 validator set registry. Reject proofs anchored to blocks with invalid or unknown proposer signatures.

Add an RPC endpoint for storing remote block headers:
- `POST /bridge/block-headers` — store a remote chain block header (with signature)

#### B5: Finality Tracking

Track block confirmations per chain:
- When a new block is received for a chain, increment confirmation counts for all previous blocks
- Mark blocks as `finality_confirmed = True` when `confirmation_count >= bridge_finality_blocks`
- In `_validate_proof`, reject proofs anchored to non-finalized blocks for transfers >= `bridge_large_transfer_threshold`

Add RPC endpoint:
- `GET /bridge/block-headers/{chain_id}/{height}` — get a stored block header with finality status

#### B6: Validator Set Epoch Tracking

Extend the v0.7.1 `BridgeValidator` table with epoch tracking:
- Add `epoch` and `is_active` columns (if not already in v0.7.1)
- Track validator set transitions with grace period
- Reject proofs signed by stale validator sets after grace period expires
- Use `ValidatorSetRegistry` from v0.7.1 Agent A for in-memory caching

#### B7: Unfence Release Path + CLI

**Unfence**: After all verification (B3-B6) is operational and tested:
- Change `bridge_release_enabled: bool = False` → `True` in `config.py`
- Update the fence comment to reflect that Merkle proof verification is now active

**CLI**: Add `oracle-status` subcommand to `cli/aitbc_cli/commands/bridge.py`:
```
aitbc bridge oracle-status
```
Reports: verification mode, finality config, validator set status, block header count per chain.

#### B8: Integration Tests

Create `apps/blockchain-node/tests/test_v072_bridge_verification.py`:
- Valid Merkle proof verification (lock event in state trie)
- Invalid Merkle proof rejection (tampered proof, wrong state root)
- Block header signature verification (valid/invalid/non-member)
- Finality threshold enforcement (small vs large transfers)
- Non-finalized block rejection for large transfers
- Validator set epoch transition with grace period
- Stale validator set rejection after grace period
- Unfenced release path — confirm/batch_confirm now work
- CLI `oracle-status` command

---

## Coordination

### Shared Files

No shared files are touched by both agents in v0.7.2. Agent A owns `aitbc/bridge/` exclusively. Agent B owns `apps/`, `cli/`, and `aitbc/constants.py`.

### Sequencing

1. **Phase 0** (prerequisite): v0.7.1 Agent B completes (BridgeValidator table, block header signature, threshold sig verification)
2. **Phase 1** (parallel): Agent A starts A1-A3 (shared SDK), Agent B starts B1-B2 (config + block header table)
3. **Phase 2** (Agent A first): Agent A completes A4 (BridgeClient + tests), Agent B starts B3-B4 (Merkle proof + block header verification — depends on A1 types + A3 utilities)
4. **Phase 3** (Agent B): B5-B8 (finality, validator epochs, unfence, CLI, tests)

### Dependencies

```
v0.7.1 Agent B (BridgeValidator, block header sig, threshold sig)
    │
    ├── A1 (types) ──┐
    ├── A2 (oracle) ─┤
    ├── A3 (verify) ─┤
    │                 ├── A4 (client + tests)
    │                 │
    ├── B1 (config) ──┐
    ├── B2 (table) ──┤
    │                 ├── B3 (Merkle proof) ──┐
    │                 ├── B4 (block header) ──┤
    │                 │                        ├── B5 (finality)
    │                 │                        ├── B6 (validator epochs)
    │                 │                        ├── B7 (unfence + CLI)
    │                 │                        └── B8 (tests)
```
