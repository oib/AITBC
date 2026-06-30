# v0.7.2 Bridge Verification — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add bridge verification config, create remote block header storage, replace field-equality proof validation with Merkle proof verification, implement block header signature verification, finality tracking, validator set epoch tracking, unfence release path, add CLI command, write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/` and `/opt/aitbc/cli/`

**Prerequisite**: v0.7.1 Agent B must be complete (BridgeValidator table, block header signature field, threshold sig verification). v0.7.0 Agent B must be committed.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/config.py apps/blockchain-node/src/aitbc_chain/base_models.py apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py apps/blockchain-node/src/aitbc_chain/rpc/bridge.py apps/blockchain-node/src/aitbc_chain/rpc/router.py cli/aitbc_cli/commands/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v072_bridge_verification.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add bridge verification config fields + constants | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `aitbc/constants.py` | ✅ |
| B2 | Create BridgeBlockHeader SQLModel table for remote chain headers | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py` (or new models file) | ✅ |
| B3 | Replace `_validate_proof` with Merkle proof verification | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B4 | Implement block header signature verification using v0.7.1 validator set | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B5 | Implement finality tracking — confirmations per chain, threshold enforcement | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B6 | Validator set epoch tracking with DB persistence + grace period | High | `apps/blockchain-node/src/aitbc_chain/base_models.py`, `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B7 | Unfence bridge release path + add CLI `oracle-status` command | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `cli/aitbc_cli/commands/bridge.py` | ✅ |
| B8 | Integration tests + verify mypy/ruff/pytest clean | High | `apps/blockchain-node/tests/test_v072_bridge_verification.py` (new) | ✅ |

---

## B1: Bridge Verification Config + Constants

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

---

## B2: Remote Block Header Storage

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

---

## B3: Merkle Proof Verification

Replace `_validate_proof` in `cross_chain/bridge.py` (lines 399-475) with:

1. **Field validation** (keep existing field equality checks)
2. **Block header lookup** — fetch `BridgeBlockHeader` from DB by `chain_id` + `block_height`
3. **State root verification** — verify `proof.state_root` matches `block_header.state_root`
4. **Merkle proof verification** — use `merkle_patricia_trie.verify_proof(key, value, proof)` against the block header's state root. The proof must include the lock event in the state trie.
5. **Block header signature verification** — use `aitbc.bridge.verification.validate_block_header()` with the v0.7.1 validator set
6. **Finality check** — use `aitbc.bridge.verification.check_finality()` with the transfer amount

Wire the `InProcessVerifier` from A2 as the verification backend, passing the blockchain node's `MerklePatriciaTrie` as the `MerkleProofVerifier`.

---

## B4: Block Header Signature Verification

Use `validate_block_header()` from A3 to verify the block header's proposer signature against the v0.7.1 validator set registry. Reject proofs anchored to blocks with invalid or unknown proposer signatures.

Add an RPC endpoint for storing remote block headers:
- `POST /bridge/block-headers` — store a remote chain block header (with signature)

---

## B5: Finality Tracking

Track block confirmations per chain:
- When a new block is received for a chain, increment confirmation counts for all previous blocks
- Mark blocks as `finality_confirmed = True` when `confirmation_count >= bridge_finality_blocks`
- In `_validate_proof`, reject proofs anchored to non-finalized blocks for transfers >= `bridge_large_transfer_threshold`

Add RPC endpoint:
- `GET /bridge/block-headers/{chain_id}/{height}` — get a stored block header with finality status

---

## B6: Validator Set Epoch Tracking

Extend the v0.7.1 `BridgeValidator` table with epoch tracking:
- Add `epoch` and `is_active` columns (if not already in v0.7.1)
- Track validator set transitions with grace period
- Reject proofs signed by stale validator sets after grace period expires
- Use `ValidatorSetRegistry` from v0.7.1 Agent A for in-memory caching

---

## B7: Unfence Release Path + CLI

**Unfence**: After all verification (B3-B6) is operational and tested:
- Change `bridge_release_enabled: bool = False` → `True` in `config.py`
- Update the fence comment to reflect that Merkle proof verification is now active

**CLI**: Add `oracle-status` subcommand to `cli/aitbc_cli/commands/bridge.py`:
```
aitbc bridge oracle-status
```
Reports: verification mode, finality config, validator set status, block header count per chain.

---

## B8: Integration Tests

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.2 — Bridge Verification
**Agent**: Agent B (Apps & Infrastructure)
