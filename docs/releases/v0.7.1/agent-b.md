# v0.7.1 Bridge Security Layer — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Create threat model doc, add bridge security config, add block header signatures, create validator set SQLModel table + RPC, upgrade bridge proof verification to multi-sig, add CLI commands, write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/` and `/opt/aitbc/cli/`

**Prerequisite**: Agent B must commit v0.7.0 work (currently uncommitted in working tree) before starting v0.7.1.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/config.py apps/blockchain-node/src/aitbc_chain/base_models.py apps/blockchain-node/src/aitbc_chain/consensus/poa.py apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py apps/blockchain-node/src/aitbc_chain/rpc/bridge.py cli/aitbc_cli/commands/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v071_bridge_security.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Create bridge threat model doc (Phase 0 prerequisite) | 🔴 P0 | `docs/architecture/bridge-threat-model.md` (new) | ✅ |
| B2 | Add bridge security config fields + constants | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `aitbc/constants.py` | ✅ |
| B3 | Add block header signature field + PoA signing/verification | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py`, `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ✅ |
| B4 | Create BridgeValidator SQLModel table + validator set cache | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py` (or new models file), `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B5 | Add validator RPC endpoints — register, get set, security status | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`, `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | ✅ |
| B6 | Upgrade bridge proof verification to multi-sig threshold | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B7 | Add CLI commands — security-status, register-validator | High | `cli/aitbc_cli/commands/bridge.py` | ✅ |
| B8 | Integration tests + verify mypy/ruff/pytest clean | High | `apps/blockchain-node/tests/test_v071_bridge_security.py` (new) | ✅ |

---

## B1: Threat Model Document

Create `docs/architecture/bridge-threat-model.md` — see Phase 0 section in overview.md for required content. This is a prerequisite for B6 (multi-sig implementation). Write it first, review it, then implement against it.

---

## B2: Bridge Security Config + Constants

In `aitbc/constants.py`, add:
```python
# Bridge multi-sig defaults (v0.7.1)
BRIDGE_MULTISIG_DEFAULT_THRESHOLD = 3    # M-of-N: minimum signatures
BRIDGE_MULTISIG_DEFAULT_VALIDATORS = 5   # N: total validators
BRIDGE_MULTISIG_TIMEOUT = 3600           # seconds to collect signatures
BRIDGE_VALIDATOR_SET_GRACE_PERIOD = 7200 # seconds — old epoch valid during rotation
BRIDGE_BLOCK_SIGNATURE_REQUIRED = True   # require block header signatures
```

In `apps/blockchain-node/src/aitbc_chain/config.py`, add to `ChainSettings` (near existing `bridge_release_enabled` at line 285):
```python
    # Bridge multi-sig configuration (v0.7.1)
    bridge_multisig_enabled: bool = False          # require multi-sig for confirm
    bridge_multisig_threshold: int = 3             # M-of-N minimum signatures
    bridge_multisig_validators: int = 5            # N total validators
    bridge_multisig_timeout: int = 3600            # seconds to collect signatures
    bridge_validator_set_grace_period: int = 7200  # seconds — old epoch valid during rotation
    bridge_block_signature_required: bool = True   # require block header signatures
```

---

## B3: Block Header Signatures

In `apps/blockchain-node/src/aitbc_chain/base_models.py`, add `signature` field to `Block` model (line 25-76):
```python
    # Block header signature (v0.7.1) — secp256k1 signature over the block hash
    # by the proposer. Empty for legacy blocks (pre-v0.7.1). Verified by PoA
    # consensus during block validation when bridge_block_signature_required=True.
    signature: str = ""
```

In `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`:
- On block proposal: sign the block hash with the proposer's private key, set `block.signature`
- On block validation: when `bridge_block_signature_required=True`, verify `block.signature` recovers to `block.proposer` using `aitbc.crypto.crypto.recover_signer()`
- Backward compatibility: if `block.signature == ""`, skip verification (legacy block)

**Important**: The proposer's private key must be available to the PoA consensus. Check how the existing PoA gets its proposer identity — likely from config or env var. If the private key is not currently available to PoA, add a `proposer_private_key` config field (loaded from env var, never logged).

---

## B4: BridgeValidator SQLModel Table

Create a `BridgeValidator` SQLModel table for persisting validator registrations:
```python
class BridgeValidator(SQLModel, table=True):
    """Bridge validator registration (v0.7.1)."""
    __tablename__ = "bridge_validators"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)           # chain this validator serves
    address: str = Field(index=True)            # checksum address
    public_key: str                             # secp256k1 public key hex
    epoch: int = Field(default=0, index=True)   # validator set epoch
    is_active: bool = Field(default=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Add a composite index on `(chain_id, epoch)` via `__table_args__` since the bridge queries by chain+epoch.

In `cross_chain/bridge.py`, add a `ValidatorSetCache` that loads from the `BridgeValidator` table into Agent A's `ValidatorSetRegistry` (from A3). The cache refreshes on epoch changes.

---

## B5: Validator RPC Endpoints

In `rpc/bridge.py`, add three new endpoints:

1. **`POST /bridge/validators/register`** — Register a validator:
   - Request: `{chain_id, address, public_key, signature}` — signature proves ownership of the address
   - Verify signature recovers to `address`
   - Store in `BridgeValidator` table
   - Update `ValidatorSetCache`
   - Response: `{status: "registered", chain_id, address, epoch}`

2. **`GET /bridge/validators/{chain_id}`** — Get validator set:
   - Optional query param `epoch` (defaults to current)
   - Response: `{chain_id, epoch, threshold, total, validators: [{address, public_key, is_active}]}`

3. **`GET /bridge/security/status`** — Security status:
   - Response: `{multisig_enabled, threshold, validator_count, current_epoch, block_signature_required, release_enabled}`

Register these endpoints in `rpc/router.py`.

---

## B6: Upgrade Bridge Proof Verification to Multi-Sig

This is the core security change. In `cross_chain/bridge.py`:

1. **Replace `_verify_proposer_signature`** (lines 477-523) with `_verify_threshold_signatures`:
   - When `bridge_multisig_enabled=True`: use Agent A's `verify_threshold_signatures()` from `aitbc.bridge.multisig`
   - When `bridge_multisig_enabled=False`: fall back to existing single-sig verification (backward compat)
   - The proof dict gains an optional `validator_signatures: list[str]` field

2. **Update `_validate_proof`** (lines 440-475) to call `_verify_threshold_signatures` instead of `_verify_proposer_signature`

3. **Update `confirm_transfer`** to check validator set exists for the source chain before proceeding. If no validator set is registered and `multisig_enabled=True`, reject with error.

4. **The `BRIDGE_RELEASE_ENABLED=false` fence stays** — multi-sig is an additional layer, not a replacement for the fence.

---

## B7: CLI Commands

In `cli/aitbc_cli/commands/bridge.py`, add two new subcommands:

1. **`bridge security-status`** — calls `BridgeClient.security_status()`, displays:
   - Multi-sig enabled/disabled
   - Threshold (M-of-N)
   - Validator count
   - Current epoch per chain
   - Block signature requirement
   - Release fence status

2. **`bridge register-validator`** — calls `BridgeClient.register_validator()`:
   - Args: `--chain-id`, `--address`, `--public-key`, `--private-key` (for signing)
   - Signs the registration request with the private key
   - Submits to `/bridge/validators/register`

---

## B8: Integration Tests

Create `apps/blockchain-node/tests/test_v071_bridge_security.py`:

- `test_block_header_signature_on_propose` — PoA signs block, signature field populated
- `test_block_header_signature_verification` — valid signature accepted
- `test_block_header_signature_invalid_rejected` — wrong signer rejected
- `test_block_header_signature_empty_legacy` — empty signature accepted (backward compat)
- `test_validator_registration` — register via RPC, verify in DB
- `test_validator_registration_invalid_signature` — bad signature rejected
- `test_get_validator_set` — get set by chain_id and epoch
- `test_validator_set_epoch_rotation` — advance epoch, old set retained for grace period
- `test_bridge_confirm_multisig_valid` — M-of-N valid sigs, confirm succeeds (if fence enabled)
- `test_bridge_confirm_multisig_insufficient` — below threshold, confirm rejected
- `test_bridge_confirm_multisig_non_member` — signer not in validator set, rejected
- `test_bridge_confirm_multisig_disabled_fallback` — multisig disabled, single sig works
- `test_bridge_confirm_release_fence` — confirm returns 503 when fence active
- `test_security_status_endpoint` — GET /bridge/security/status returns config
- `test_cli_security_status` — CLI command output
- `test_cli_register_validator` — CLI command submits registration

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.1 — Bridge Security Layer
**Agent**: Agent B (Apps & Infrastructure)
