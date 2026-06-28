# v0.5.16 — Agent Task Assignment (Remaining Work)

**Release Theme**: Security Hardening & Multi-Chain Preparation — *closure pass*. The bulk of v0.5.16 (Bugs 1, 4, 7, 8, 11, 16, 17, 18 and the Bug 3/12 partial) has already been implemented (commit `3d94338c2`). This document covers only the **verified residual gaps** needed to actually close v0.5.16, plus one **newly discovered regression** introduced by the Bug 4 signature-verification fix.

**Goal**: Finish the v0.5.16 security work — make transaction signing/verification consistent end-to-end, close the remaining auth/chain_id/port gaps in `apps/`, fence off the not-yet-secure bridge release path, and update release tracking to reflect reality.

> **Scope note**: Full bridge proposer-set tracking + Merkle proof verification remain in **v0.7.2** (as planned). This release only adds a safety fence + the shared crypto primitive that v0.7.2 will build on.

---

## Status Baseline — Already Done (verified, do NOT redo)

| Bug | Item | Evidence | Status |
|-----|------|----------|--------|
| 1 | `TransactionRequest.chain_id` field + used in `submit_transaction` | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py:24,91` | ✅ DONE |
| 4 | Tx signature verification on `/rpc/transaction` | `rpc/transactions.py:106-108` (see **A1/B6 regression** below) | ⚠️ DONE but broke ed25519 callers |
| 7 | Bridge lock/confirm signature checks | `rpc/bridge.py:44-57,110-117` | ✅ DONE |
| 8 | Staking signature checks | `rpc/staking.py:45-51,100-106` | ✅ DONE |
| 11 | `contracts_stub.py` raises 503 instead of fake success | `rpc/contracts_stub.py` | ✅ DONE |
| 3/12 | Bridge proof: chain_id + block anchor + signature *recovery* | `cross_chain/bridge.py:258-315` | ⚠️ PARTIAL — accepts **any** valid signer (see B1) |
| 6 | `MultiChainManager` import-crash | rewritten; imports only real classes, no `# type: ignore` | ✅ OBSOLETE (now just dead code → v0.6.4) |
| 16 | agent-coordinator chain_id + port 8006 | `agent-coordinator/.../websocket/agent_stream.py:358-376` | ✅ DONE |
| 17/18 | marketplace direct-SQLite → RPC | `marketplace_service/services/marketplace_service.py:208-276` | ✅ DONE |

---

## Task Split Overview

| Agent | Domain | Tasks | Files Touched |
|-------|--------|-------|---------------|
| **Agent A** | Type safety & shared core (`aitbc/`) | 4 items | `aitbc/crypto/*`, `tests/unit/` |
| **Agent B** | Bug fixes, infrastructure & apps | 9 items | `apps/blockchain-node`, `apps/marketplace`, `apps/gpu`, `cli/`, docs, root `AGENTS.md` |

**Conflict boundary** (from root `AGENTS.md`): Agent A owns all files under `aitbc/` except `aitbc/constants.py` and `aitbc/log_utils/`. Agent B owns all `apps/` files, `cli/` files, `aitbc/constants.py`, `aitbc/log_utils/`, docs, and systemd config. **Both agents must not edit the same file.** The signing-scheme work (A1 ↔ B6) is split across two different files joined by a shared wire-format contract — see Coordination Protocol.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Make the shared cross-service transaction builder produce signatures the blockchain node actually accepts, require `chain_id`, and expose one canonical signature-verification primitive.

**Working directory**: `/opt/aitbc/aitbc/crypto/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | **Regression:** `TransactionService` signs with **ed25519** but the node verifies **secp256k1** → all shared-helper callers are now rejected by the Bug 4 check. Switch signing to secp256k1/eth-account. | 🔴 P0 | `aitbc/crypto/transaction_service.py` | ✅ DONE |
| A2 | Require & validate `chain_id` in `generate_signed_transaction` — log+raise instead of silently sending `chain_id: ""`. | High | `aitbc/crypto/transaction_service.py` | ✅ DONE |
| A3 | Expose a canonical `recover_signer(message_data: dict, signature: str) -> str \| None` in `aitbc/crypto/` so apps share one implementation (removes the 3 duplicated copies). | Medium | `aitbc/crypto/crypto.py`, `aitbc/crypto/__init__.py` | ✅ DONE |
| A4 | Unit tests for A1–A3 + keep mypy/ruff clean. | High | `tests/unit/test_transaction_service.py` (new) | ✅ DONE |

### Agent A — Detailed Instructions

#### A1: Fix the signing-scheme regression (P0)
- **Problem**: `generate_signed_transaction()` (<ref_snippet file="/opt/aitbc/aitbc/crypto/transaction_service.py" lines="90-102" />) signs with `ed25519.Ed25519PrivateKey` producing a 64-byte signature. The node's `verify_transaction_signature` (<ref_snippet file="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/utils.py" lines="38-47" />) does secp256k1 `ecrecover` and rejects anything that isn't 65 bytes. Result: agent-coordinator coin requests and CLI transfers signed via this helper now fail with `403 Invalid transaction signature`.
- **Fix**: Sign with secp256k1 using **`eth_keys`** (not eth-account — see ⚠️ below). The signed payload **must** match the verifier exactly:
  - message = `keccak256( json.dumps(<signed fields>, sort_keys=True, separators=(",", ":")) )`
  - **signed fields = `{from, to, amount, fee, nonce, payload, type}`** — verified against the real endpoint: it reconstructs `tx_data_dict` from the Pydantic model and strips only `signature`. `chain_id` is **NOT** in the signed set.
  - **`payload` defaulting**: for an alias-posted (`from`/`to`) TRANSFER, the server's `validate_payload` injects only `amount` (it checks `"recipient" in values`, which is false for alias input). So sign over `payload = {"amount": amount}`.
  - signature = 65-byte `r‖s‖v` hex; recovered address must equal `from`.
- **✅ Implementation note (done, verified)**:
  - Signing **must** use `eth_keys` (`PrivateKey.sign_msg_hash(...).to_bytes()`), **not** eth-account `sign_hash`/`unsafe_sign_hash`. eth-account emits `v=27/28`, but the verifier's `keys.Signature(sig_bytes)` requires `v∈{0,1}` and raises `BadSignature('Value 27 is not less than or equal to 1')` → rejected. (Empirically confirmed against the real verifier.) The original "mirror `sign_transaction_hash`" guidance above is therefore **wrong** and was not followed.
  - Added module helper `_canonical_signing_message()` + `_SIGNED_FIELDS` so the wire format is pinned and testable.
  - **Fail closed**: if `GENESIS_ADDRESS` ≠ the secp256k1 address derived from `GENESIS_PRIVATE_KEY`, return `None` with an explicit error rather than emit an unverifiable tx.
  - Tests: <ref_file file="/opt/aitbc/tests/unit/test_transaction_service.py" /> (5 tests, incl. an end-to-end check against the **real** `verify_transaction_signature` + `TransactionRequest`). mypy + ruff clean.
- **⚠️ Follow-up discovered during A1 (now tracked as B9)**: the system has a **conflicting key model**. Genesis/keystore tooling (`apps/blockchain-node/scripts/create_genesis_wallet.py`, `keystore.py`, `unified_genesis.py`) generates **ed25519** keys with `ait1`+`sha256(pubkey)` addresses, while the Bug 4 verifier + `aitbc/crypto/crypto.py` + most addresses are **secp256k1 `0x`** eth-style. A1 makes the signer match the (dominant, authoritative) secp256k1 verifier, but **transactions from an ed25519 genesis wallet still won't verify**. **Decision (user-approved)**: migrate genesis/keystore tooling to secp256k1 — see **B9** for the full task. The chain_id-not-signed gap (above) should be closed in **B6** (extend the signed set to cover `chain_id`).
- **Coordination**: the message format is the shared contract with Agent B (B6) — see the updated Coordination Protocol. The B6 round-trip test must use `eth_keys`-signed txs.

#### A2: Require chain_id
- In `generate_signed_transaction`, after resolving `actual_chain_id = chain_id or self.chain_id`, if it is empty/`None`: log an error and return `None` (or raise `ValueError`) — never emit `chain_id: ""`.
- Keep the signature param backward-compatible (`chain_id: str | None = None`), but fail closed when it can't be resolved.

#### A3: Canonical recover/verify primitive
- Add `recover_signer(message_data: dict[str, Any], signature: str) -> str | None` to `aitbc/crypto/crypto.py` (keccak256 of canonical JSON → eth-account recover → checksum address; return `None` on any failure). Export it from `aitbc/crypto/__init__.py`.
- This is the single implementation that Agent B will migrate `verify_transaction_signature`, `verify_request_signature`, and `_verify_proposer_signature` onto (B6/B1). Keep the existing `verify_signature(message_hash, signature, address)` intact for current callers.

#### A4: Tests
- New `tests/unit/test_transaction_service.py`: sign a tx with the genesis key, assert `recover_signer(...) == from` and that the produced signature is 65 bytes; assert `generate_signed_transaction` returns `None` when chain_id unresolved.

---

## Agent B — Apps, Infrastructure & Docs

**Scope**: Close the residual auth / chain_id / port gaps in `apps/`, fence off the not-yet-secure bridge release path, complete the verifier side of the signing-scheme fix, and update release tracking.

**Working directory**: `/opt/aitbc/` (cross-cutting)

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ && \
  cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" ; cd ../.. ; \
  cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | **Security:** Bridge proof accepts **any** valid signer (no proposer-set check). Fence the mint/release path behind a default-off feature flag; reclassify Bug 3 in code/comments as PARTIAL. | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py`, `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`, `apps/blockchain-node/src/aitbc_chain/config.py` | ✅ DONE |
| B2 | **Bug 9 (partial):** `/mining/miners` has no auth (the other 3 mining endpoints do). | High | `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | ✅ DONE |
| B3 | **Bug 10:** 7 silent `except ImportError` blocks set features to `None`. Log explicit startup warnings; add fail-fast option. | High | `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | ✅ DONE |
| B4 | **Bug 15 (partial):** marketplace defaults to wrong RPC port `8202`. | High | `apps/marketplace/src/marketplace_service/main.py` | ✅ DONE |
| B5 | **chain_id family:** GPU `GPU_REGISTER` tx submitted without `chain_id`. | High | `apps/gpu/src/gpu_service/main.py` | ✅ DONE |
| B6 | **Regression (verifier side):** ensure `verify_transaction_signature` message construction matches A1; add a sign→submit→verify round-trip test. | 🔴 P0 | `apps/blockchain-node/tests/test_signing_round_trip.py` (new) | ✅ DONE |
| B7 | **Bug 14:** confirm `TRUST_X_WALLET_ADDRESS` defaults false (already true) + add dev-only note to config example/docs. | Medium | `examples/blockchain.env.example` | ✅ DONE |
| B8 | Update `v0.5.16/change.log` status (mark fixed bugs ✅, Bug 3 PARTIAL) + root `AGENTS.md` release tracking (v0.5.16/v0.5.17 → Completed). | Low | `docs/releases/v0.5.16/change.log`, `AGENTS.md` | ✅ DONE |
| B9 | **Key model migration:** Genesis/keystore tooling generates **ed25519** keys with `ait1`+`sha256(pubkey)` addresses, incompatible with the secp256k1/`0x` verifier (Bug 4) and A1 signer. Migrate all genesis/keystore/wallet key generation to secp256k1 with Ethereum-style `0x` addresses. **Breaking** — requires genesis regeneration for existing deployments. | 🔴 P0 | `apps/blockchain-node/scripts/create_genesis_wallet.py`, `unified_genesis.py`, `keystore.py`, `setup_production.py`, `apps/coordinator-api/.../wallet_adapter_enhanced.py`, `cli/aitbc_cli/commands/wallet/basic.py`, `cli/aitbc_cli/utils/crypto_utils.py`, tests, examples, docs | ⬜ TODO |

### Agent B — Detailed Instructions

#### B1: Fence the bridge release path (P0)
- **Problem**: `_verify_proposer_signature` (<ref_snippet file="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py" lines="350-357" />) recovers a signer but accepts **any** valid signature — it never checks the recovered address is an authorized source-chain proposer. A proof signed by any attacker-generated key passes. The mint/release path is therefore drainable until v0.7.2 adds proposer-set tracking.
- **Fix (this release)**:
  - Gate `confirm_transfer` / the unlock-mint path behind a setting that defaults **off** (e.g. `BRIDGE_RELEASE_ENABLED=false`); return `503 bridge release disabled` when off.
  - Update the misleading comment ("non-forgeable without a private key") to state the real limitation and reference v0.7.2.
  - Reclassify Bug 3 as **PARTIAL** in the change.log (B8).
- **Do NOT** attempt full proposer-set verification here — that is v0.7.2. (After A3 lands, migrate `_verify_proposer_signature` to call `aitbc.crypto.recover_signer` so v0.7.2 only has to add the set-membership check.)

#### B2: Bug 9 — authenticate `/mining/miners`
- Add `get_authenticated_address(request, credentials)` to `list_miners_route` (<ref_snippet file="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py" lines="907-913" />), matching `/mining/start|stop|status` (lines 855/880/896).

#### B3: Bug 10 — no more silent feature disabling
- 7 `try/except ImportError` blocks in `rpc/router.py` (≈lines 44-204) set disputes/contracts/islands/bridge/staking/gpu functions to `None` silently.
- For each: `logger.warning("RPC feature '<x>' disabled: %s", exc)` at import time, and register a `503` fallback route (don't 404 silently). Add `RPC_REQUIRE_ALL_FEATURES=true` to fail-fast on startup when any required module is missing.

#### B4: Bug 15 — marketplace port
- <ref_snippet file="/opt/aitbc/apps/marketplace/src/marketplace_service/main.py" lines="19-19" />: change default `http://localhost:8202` → `http://localhost:8006` (blockchain-node RPC). Grep the marketplace package for any other `8202` literals.

#### B5: GPU chain_id
- The `GPU_REGISTER` tx dict in `gpu_service/main.py` (≈lines 272-291) has no `chain_id`. Add `"chain_id": os.getenv("CHAIN_ID", "") or DEFAULT_CHAIN_ID`. Same class as Bug 16; completes the cross-service chain_id family. (Relies on the v0.5.16 `TransactionRequest.chain_id` field, already present.)

#### B6: Verifier side of the signing-scheme fix (P0)
- Confirm `verify_transaction_signature` builds the message identically to A1: `keccak256(json.dumps(tx_without "signature", sort_keys=True, separators=(",",":")))`, 65-byte sig, recovered == `from`.
- Add an integration test under `tests/integration/` that calls `TransactionService.generate_signed_transaction(...)` then drives `/rpc/transaction` (via the multi-node harness `TestClient`) and asserts **acceptance** (not 403). This is the regression guard for A1↔B6.

#### B7: Bug 14 — document dev-only header trust
- `auth.py` already defaults `TRUST_X_WALLET_ADDRESS` to false and warns when enabled (<ref_snippet file="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/auth.py" lines="35-49" />) — no code change. Add a dev-only warning comment to the relevant `examples/*.env` and a sentence in the bridge/node docs.

#### B8: Release tracking
- `v0.5.16/change.log`: set per-bug status (✅ for done items in the Status Baseline above; **PARTIAL** for Bug 3 with the B1 fence noted), flip header `Status` from `🚧 Planned` to `🚧 In Progress`/`✅ Complete` as appropriate.
- Root `AGENTS.md`: move v0.5.16 and v0.5.17 out of "Planned Releases / Immediate Bugfix" into "Completed Releases", and correct the stale "Verified Code Targets … STILL PRESENT" claims for the already-fixed bugs (and Bug 6 import-crash, now obsolete).

#### B9: Migrate genesis/keystore key generation to secp256k1 (P0)

> **Decision (user-approved)**: secp256k1 is the canonical key model. Migrate genesis tooling to match the Bug 4 verifier and A1 signer. Rejected alternatives: curve-agnostic verifier (permanent dual-path maintenance tax), revert Bug 4 to ed25519 (discards EVM compatibility), defer indefinitely (system can't move real value).

**Problem**: All genesis/keystore scripts generate ed25519 keys and derive addresses as `sha256(pubkey)[:20].hex()` with `ait1` or `aitbc1` prefix. The node's transaction verifier (Bug 4 fix) and A1 signer use secp256k1 with Ethereum-style `keccak256(pubkey)[-20:]` + `0x` addresses. A1 made the signer correct, but a genesis wallet created by the existing tooling produces an ed25519 private key and an `ait1` address — `eth_keys.PrivateKey(bytes.fromhex(...))` will derive a *different* `0x` address, A1's fail-closed check rejects the mismatch, and no genesis-funded transaction can be signed. This task makes genesis key generation consistent with the verifier.

**NOT in scope** (explicitly excluded to prevent scope creep):
- **Agent receipt signing** (`packages/py/aitbc-crypto/src/aitbc_crypto/signing.py`, `packages/py/aitbc-sdk/src/aitbc_sdk/receipts.py`) — these use ed25519 for agent-to-agent receipt signatures, a separate system from blockchain transaction signing. Leave as-is.
- **Wallet app encryption** (`apps/wallet/src/app/crypto/encryption.py`) — uses nacl XChaCha20-Poly1305 for symmetric encryption, not key generation. Keep nacl for encryption; only change the key *generation* algorithm.
- **`aitbc/crypto/crypto.py`** — already has `derive_ethereum_address()` using eth_account. No change needed (Agent A domain).

**Sub-tasks** (all Agent B domain — `apps/`, `cli/`):

**B9a — Genesis scripts** (5 files in `apps/blockchain-node/scripts/`):
1. `create_genesis_wallet.py` (lines 11, 31-32, 16-23, 42):
   - Replace `ed25519.Ed25519PrivateKey.from_private_bytes(...)` with `eth_account.Account.from_key(...)` (or `eth_keys.keys.PrivateKey(...)`).
   - Replace `derive_address_from_public_key()` (sha256→aitbc1) with `aitbc.crypto.crypto.derive_ethereum_address()` (already exists, returns `0x` checksum address) or inline equivalent: `Account.from_key(priv_key).address`.
   - Remove the `aitbc1`→`ait1` prefix swap (line 42). Address is now `0x...` directly.
   - Store `private_key.hex()` (64 hex chars, no `0x` prefix) in the encrypted keystore — this is what `TransactionService` expects via `GENESIS_PRIVATE_KEY`.
   - Set `"keytype": "secp256k1"` in wallet_data (was implicitly ed25519).
   - Keep AES-GCM + PBKDF2 encryption as-is (encryption layer is curve-independent).

2. `unified_genesis.py` (lines 23, 53-54, 35-39, 62):
   - Same changes as `create_genesis_wallet.py`.
   - The `ait_address = address.replace("aitbc1", "ait1")` line (62) becomes a no-op — address is already `0x...`.
   - Genesis allocations (line 131-137) will now use `0x` addresses — consistent with what the node expects.

3. `keystore.py` (lines 5, 30-31, 36-47, 76, 82-91, 126-130):
   - Replace `ed25519.Ed25519PrivateKey.generate()` with `eth_account.Account.create()`.
   - Replace `generate_address()` (bech32 `ait` HRP + sha256) with Ethereum address derivation (`account.address`).
   - Change `"keytype": "ed25519"` → `"keytype": "secp256k1"`.
   - In `show_keyinfo()`: replace `ed25519.Ed25519PrivateKey.from_private_bytes(...)` with `Account.from_key(...)`.
   - Private key bytes: eth_account stores 32-byte raw private key; encrypt/decrypt that directly (same AES-GCM flow works).
   - **Decision**: drop bech32 encoding entirely (remove `bech32` import) — `0x` checksum addresses are the standard going forward.

4. `setup_production.py` (lines 25, 69, 75-76):
   - Same pattern as `keystore.py`. Replace ed25519 generation + bech32 address with secp256k1 + `0x`.

5. `make_genesis.py` (line 63):
   - Reads allocations JSON with `ait1` addresses. No key generation, but update any example/default allocations to `0x` format. The script itself is format-agnostic (just passes addresses through), so minimal change.

**B9b — Address validation & prefix checks** (3 files in `apps/`):
1. `apps/coordinator-api/src/app/agent_identity/wallet_adapter_enhanced.py` (lines 599, 719, 723, 754):
   - `_derive_address_from_private_key()` (line 749-754): replace `sha256(private_key)[:32]` + `ait1` prefix with `Account.from_key(private_key).address` (secp256k1 → `0x`).
   - Address validation (line 719-723): change `startswith("ait1")` check to `startswith("0x")` + length 42 + checksum validation (`eth_utils.is_checksum_address`).
   - Line 599: `address = f"ait1{key_hash}"` → use `derive_ethereum_address()`.

2. `apps/coordinator-api/src/app/contexts/cross_chain/routers/cross_chain_integration.py` (line 62):
   - `if not owner_address.startswith("ait1")` → `if not owner_address.startswith("0x")`.

3. `apps/bridge-monitor/src/bridge_monitor/main.py` (line 59):
   - `if decoded.startswith("ait1") or decoded.startswith("aitbc1")` → `if decoded.startswith("0x")`.

**B9c — CLI wallet** (2 files in `cli/`):
1. `cli/aitbc_cli/commands/wallet/basic.py` (lines 48, 582, 589):
   - HD wallet path (line 48) already uses `ec.SECP256K1()` — good, but derives address as `aitbc1{sha256[:20]}`. Change to Ethereum `0x` address derivation.
   - Simple wallet path (lines 582, 589): replace fake key generation + `ait1` address with real `Account.create()` + `0x` address.

2. `cli/aitbc_cli/utils/crypto_utils.py` (lines 238-239):
   - `bech32_to_hex()` with `ait1` prefix handling: update to handle `0x` prefix directly (or keep `ait1`→hex as a legacy compat path with a deprecation warning).
   - If removing bech32 entirely, update `hex_to_bech32()` callers.

**B9d — Tests** (update mocks + key generation):
1. `tests/verification/test_keystore_mac.py` (lines 16, 41, 91, 121, 166):
   - Replace `ed25519.Ed25519PrivateKey.generate()` with `Account.create()`.
   - MAC computation (HMAC-SHA256 over derived_key[16:32] + ciphertext) is encryption-layer, stays the same.

2. `tests/verification/test_agent_signature_verification.py` (lines 11, 15, 20, 49, 52, 78, 145, 185):
   - ⚠️ **Check scope first**: if these test *agent receipt* signatures (ed25519), they should stay ed25519 (out of scope, see above). If they test *blockchain transaction* signatures, migrate to secp256k1. Read the file before changing.

3. `tests/cli/test_crypto_utils.py` (lines 179-185):
   - Update `test_bech32_to_hex_ait1_prefix` to test `0x` prefix instead.

4. CLI test mocks with `ait1` addresses — update to `0x` addresses:
   - `tests/cli/test_commands_wallet.py` (line 88)
   - `tests/cli/test_commands_transactions.py` (lines 115, 154, 177)
   - `tests/cli/test_commands_operations.py` (lines 163, 167)
   - `tests/cli/test_commands_mining.py` (lines 86, 105)
   - `tests/cli/test_commands_messaging.py` (lines 58, 65, 79)
   - `tests/cli/test_commands_edge.py` (line 92)
   - `tests/cli/test_commands_contract.py` (lines 73, 75)
   - `tests/cli/test_commands_account.py` (lines 52, 58, 65, 71, 77, 124)
   - `tests/fixtures/cli_mocks.py` (lines 59, 60, 76, 77, 83)
   - `tests/conftest.py` (line 87)
   - Use valid checksum `0x` addresses (e.g. `Account.create().address`) or well-known test addresses.

**B9e — Examples & docs** (update `ait1` → `0x` in env examples):
1. `examples/blockchain.env.example` (lines 40, 41) — replace `ait1` addresses with `0x` addresses.
2. `examples/blockchain.env.open-island` (lines 6, 22) — same.
3. `apps/blockchain-node/create_enhanced_genesis.py` (line 75) — hardcoded `ait1devproposer...` → real `0x` test address or derive from a test key.
4. `apps/blockchain-node/scripts/create_bootstrap_genesis.py` (lines 21-45) — `aitbc`-prefixed static addresses → `0x` format.
5. `apps/blockchain-node/scripts/keygen.py` (line 25) — fake `ait1` address → `Account.create().address`.

**Verification for B9**:
```bash
# 1. Generate a genesis wallet and verify the address is 0x + key is secp256k1
./venv/bin/python apps/blockchain-node/scripts/create_genesis_wallet.py
# Check: output address starts with "0x", is 42 chars, is valid checksum

# 2. Verify the generated key works with TransactionService (A1 end-to-end)
GENESIS_PRIVATE_KEY=<generated_key> GENESIS_ADDRESS=<generated_address> \
  ./venv/bin/python -m pytest tests/unit/test_transaction_service.py -q -o addopts=""

# 3. Run keystore round-trip
./venv/bin/python apps/blockchain-node/scripts/keystore.py --name test --create --password testpass
./venv/bin/python apps/blockchain-node/scripts/keystore.py --name test --show --password testpass
# Check: address is 0x format

# 4. Full test suite
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit tests/cli tests/verification -q -o addopts=""
cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

**Operational note (for B8 changelog)**: This is a **breaking change for existing deployments**. Any chain running with ed25519 genesis wallets must:
1. Regenerate the genesis wallet (`create_genesis_wallet.py` or `unified_genesis.py --force --create-wallet`).
2. Update `GENESIS_ADDRESS` and `GENESIS_PRIVATE_KEY` env vars with the new `0x` address and secp256k1 key.
3. Reinitialize the chain database (genesis allocations now use `0x` addresses).
4. Any pre-existing account balances keyed to `ait1` addresses are orphaned — this is expected for a key-model migration.

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/crypto/transaction_service.py` | Agent A | A1 (secp256k1) + A2 (require chain_id) |
| `aitbc/crypto/crypto.py`, `aitbc/crypto/__init__.py` | Agent A | A3 `recover_signer` |
| `tests/unit/test_transaction_service.py` | Agent A | A4 (new file) |
| `apps/blockchain-node/.../cross_chain/bridge.py` + `rpc/bridge.py` | Agent B | B1 fence |
| `apps/blockchain-node/.../rpc/router.py` | Agent B | B2 + B3 (apply together) |
| `apps/blockchain-node/.../rpc/utils.py` | Agent B | B6 verifier |
| `apps/marketplace/.../main.py` | Agent B | B4 port |
| `apps/gpu/.../main.py` | Agent B | B5 chain_id |
| `tests/integration/` round-trip test | Agent B | B6 (new file, separate from A4) |
| `docs/releases/v0.5.16/change.log`, root `AGENTS.md` | Agent B | B8 |
| `apps/blockchain-node/scripts/{create_genesis_wallet,unified_genesis,keystore,setup_production,make_genesis,keygen}.py` | Agent B | B9a (genesis key migration) |
| `apps/coordinator-api/.../wallet_adapter_enhanced.py`, `cross_chain_integration.py`, `apps/bridge-monitor/.../main.py` | Agent B | B9b (address validation) |
| `cli/aitbc_cli/commands/wallet/basic.py`, `cli/aitbc_cli/utils/crypto_utils.py` | Agent B | B9c (CLI wallet) |
| `tests/verification/test_keystore_mac.py`, `tests/cli/test_crypto_utils.py`, `tests/cli/test_commands_*.py`, `tests/fixtures/cli_mocks.py`, `tests/conftest.py` | Agent B | B9d (test mocks) |
| `examples/*.env`, `apps/blockchain-node/create_enhanced_genesis.py`, `apps/blockchain-node/scripts/create_bootstrap_genesis.py` | Agent B | B9e (examples/docs) |

No file is edited by both agents. The only cross-agent dependency is the **wire-format contract** for transaction signatures.

### Shared Contract — Transaction Signature Wire Format (A1 ↔ B6) — VERIFIED
Both sides MUST agree, byte-for-byte (confirmed against the real verifier in A1):
1. **Curve**: secp256k1, signed with **`eth_keys`** (`PrivateKey.sign_msg_hash`). ⚠️ Do **not** use eth-account `sign_hash` — it emits `v=27/28` which `eth_keys.Signature` rejects (`v` must be `0/1`).
2. **Signed fields**: exactly `{from, to, amount, fee, nonce, payload, type}` — i.e. the endpoint's `tx_data_dict` minus `signature`. **`chain_id` is excluded** (latent malleability gap → close in B6).
3. **Message**: `keccak256( json.dumps(<signed fields>, sort_keys=True, separators=(",", ":")) )`.
4. **`payload` defaulting**: alias-posted (`from`/`to`) TRANSFER → server injects only `amount`; sign over `payload={"amount": amount}`.
5. **Signature**: 65-byte `r‖s‖v` hex (optionally `0x`-prefixed); recovered checksum address == `from`.
If either side needs to change this, update this section first and re-run the B6 round-trip test.

### Execution Order

1. **Phase 1 (parallel, no dependencies)**
   - Agent A: **A1, A2, A3** (all in `aitbc/crypto/`).
   - Agent B: **B1, B2, B3, B4, B5, B7** (independent `apps/` fixes).
   - Agent B: **B9a–B9e** (genesis key migration — can start in parallel; no dependency on A1 since it changes key *generation*, not signing).
2. **Phase 2 (sequential — depends on Phase 1)**
   - Agent B: **B6** verifier alignment + round-trip test (needs A1 merged **and B9a merged** — the round-trip test needs a secp256k1 genesis key to actually pass end-to-end).
   - Agent B: migrate `_verify_proposer_signature` to `aitbc.crypto.recover_signer` (needs A3 merged) — optional polish on B1.
   - Agent A: **A4** unit tests (can start in Phase 1, finalize once A1 stable).
3. **Phase 3 (wrap-up)**
   - Agent B: **B8** changelog + AGENTS.md tracking (must document B9 as a breaking change requiring genesis regeneration).
   - Both: run full verification commands; confirm `apps/coordinator-api` and `apps/blockchain-node` suites green.

### Definition of Done
- [ ] A round-trip test proves a `TransactionService`-signed tx is **accepted** by `/rpc/transaction` (A1 + B6 + B9a — needs a secp256k1 genesis key).
- [ ] `chain_id` cannot be silently dropped from a shared-helper transaction (A2) and GPU registers with chain_id (B5).
- [ ] `/mining/miners` requires auth (B2); silent import failures are logged, not hidden (B3); marketplace points at `:8006` (B4).
- [ ] Bridge release path is default-off and Bug 3 is documented as PARTIAL pending v0.7.2 (B1, B8).
- [ ] Genesis/keystore scripts generate secp256k1 keys with `0x` addresses; generated keys pass A1's fail-closed check and produce verifiable transactions (B9a).
- [ ] Address validation across `apps/` and `cli/` accepts `0x` addresses; no `ait1` prefix checks remain in production code (B9b, B9c).
- [ ] All test mocks use `0x` addresses; test suites pass (B9d).
- [ ] `mypy aitbc/` + `ruff check` clean; blockchain-node & coordinator-api test suites pass.

---

*Last Updated: 2026-06-29*
*Version: 0.5.16 (remaining-work closure + key model migration)*
*Status: Planned*
