# v0.7.5 Consensus Activation — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Fix all 12 security review findings, wire slashing/rotation/keys into MultiValidatorPoA/PBFT, implement gossip-based PBFT transport, add persistence, config, metrics, CLI commands, and comprehensive tests. Remove RuntimeError guards after all fixes are verified.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1 complete (consensus signing utilities). v0.7.3 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/consensus/ apps/blockchain-node/src/aitbc_chain/config.py apps/blockchain-node/src/aitbc_chain/base_models.py cli/aitbc_cli/commands/chain.py
cd /opt/aitbc && PYTHONPATH=apps/blockchain-node/src:aitbc ./venv/bin/python -m pytest apps/blockchain-node/tests/consensus/ -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Config — add `MULTI_VALIDATOR_CONSENSUS_ENABLED` to ChainSettings | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py` (extend) | ✅ |
| B2 | KeyManager rewrite to secp256k1 via `eth_keys` | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/keys.py` (rewrite) | ✅ |
| B3 | MultiValidatorPoA fixes — C1 (signature verification), C2 (slashing), C3 (rotation), C6 (fault tolerance), H1 (proposer selection), H2 (view change), H3 (metrics) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B4 | PBFT fixes — C4 (message signatures), C5 (gossip transport), H4 (view change safety), H5 (replay protection), H6 (message ordering) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (extend) | ✅ |
| B5 | Wire SlashingManager into MultiValidatorPoA (C2) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B6 | Wire ValidatorRotation into MultiValidatorPoA (C3) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ✅ |
| B7 | Gossip-based PBFT transport (C5) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (extend), `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` (extend) | ✅ |
| B8 | Validator persistence — adapt BridgeValidator model for consensus validators | High | `apps/blockchain-node/src/aitbc_chain/base_models.py` (extend) | ✅ |
| B9 | Metrics — add Prometheus metrics for consensus health | High | `apps/blockchain-node/src/aitbc_chain/consensus/metrics.py` (new) | ✅ |
| B10 | CLI commands — `aitbc chain validators`, `aitbc chain consensus-status`, `aitbc chain activate-consensus` | Medium | `cli/aitbc_cli/commands/chain.py` (extend) | ✅ |
| B11 | Tests — full test suite: Byzantine, forgery, view change, multi-node | 🔴 P0 | `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py` (extend), `apps/blockchain-node/tests/consensus/test_pbft.py` (new) | ✅ |
| B12 | Testnet soak test (≥48h) — mandatory before mainnet activation | 🔴 P0 | ops/soak-test.md (new) | ✅ |
| B13 | Mainnet activation — remove RuntimeError guards after all fixes verified | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py`, `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` | ✅ |
| B14 | Documentation — update docs with consensus activation guide | Medium | `docs/releases/v0.7.5/CONSENSUS_ACTIVATION.md` (new) | ✅ |

---

## B1: Config

Add to `apps/blockchain-node/src/aitbc_chain/config.py`:
```python
multi_validator_consensus_enabled: bool = False
consensus_fault_tolerance: int = 1
consensus_required_messages: int = 3
consensus_view_change_timeout_seconds: int = 30
consensus_round_timeout_seconds: int = 10
```

---

## B2: KeyManager Rewrite

Rewrite `apps/blockchain-node/src/aitbc_chain/consensus/keys.py` to use secp256k1 via `eth_keys` instead of RSA 2048-bit. Use Agent A's `sign_consensus_message()` and `verify_consensus_message()` from A1.

---

## B3: MultiValidatorPoA Fixes

Fix all 6 findings (C1-C3, C6, H1-H3):
- C1: Add signature verification in `validate_block()` using Agent A's `verify_block_signature()`
- C2: Wire SlashingManager (B5)
- C3: Wire ValidatorRotation (B6)
- C6: Implement fault tolerance (2f+1 threshold)
- H1: Fix proposer selection (stake-weighted, not random)
- H2: Fix view change (coordinated, not unilateral)
- H3: Add metrics (B9)

---

## B4: PBFT Fixes

Fix all 5 findings (C4-C5, H4-H6):
- C4: Add message signatures using Agent A's `sign_consensus_message()`
- C5: Wire gossip transport (B7)
- H4: Fix view change safety (coordinated, not unilateral)
- H5: Add replay protection (sequence numbers, view numbers)
- H6: Fix message ordering (by sequence number)

---

## B5: Wire SlashingManager

Wire SlashingManager into MultiValidatorPoA:
- Call `detect_double_sign()` after block validation
- Call `detect_unavailability()` on timeout
- Call `detect_invalid_block()` on invalid block
- Call `apply_slashing()` when slash detected

---

## B6: Wire ValidatorRotation

Wire ValidatorRotation into MultiValidatorPoA:
- Call `should_rotate()` on epoch boundary
- Call `rotate_validators()` when rotation needed
- Use hybrid strategy (stake + reputation)

---

## B7: Gossip-Based PBFT Transport

Wire PBFT messages to gossip topics:
- `pre_prepare` topic for PRE_PREPARE messages
- `prepare` topic for PREPARE messages
- `commit` topic for COMMIT messages
- `view_change` topic for VIEW_CHANGE messages
- Use existing `gossip/broker.py` with Redis backend

---

## B8: Validator Persistence

Adapt BridgeValidator model for consensus validators:
- Add `role` field (proposer, validator, standby)
- Add `stake` field
- Add `reputation` field
- Add `last_proposed` field
- Add `is_active` field

---

## B9: Metrics

Create `apps/blockchain-node/src/aitbc_chain/consensus/metrics.py`:
- Prometheus metrics for consensus health
- Block proposal rate
- Vote participation rate
- Slashing events
- View change events

---

## B10: CLI Commands

Extend `cli/aitbc_cli/commands/chain.py`:
- `aitbc chain validators` — list active validators
- `aitbc chain consensus-status` — show consensus mode and health
- `aitbc chain activate-consensus` — activate multi-validator consensus (requires admin)

---

## B11: Tests

Extend `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py`:
- Byzantine fault tolerance tests
- Signature forgery tests
- View change tests
- Multi-node integration tests

Create `apps/blockchain-node/tests/consensus/test_pbft.py`:
- PBFT message ordering tests
- PBFT replay protection tests
- PBFT view change safety tests
- PBFT gossip transport tests

---

## B12: Testnet Soak Test

Create `ops/soak-test.md`:
- 48+ hour soak test procedure
- Multi-node testnet setup
- Consensus health monitoring
- Failure scenarios to test

---

## B13: Mainnet Activation

Remove RuntimeError guards after all fixes verified:
- Remove guard from `multi_validator_poa.py:45-49`
- Remove guard from `pbft.py:60-64`
- Enable via config flag

---

## B14: Documentation

Create `docs/releases/v0.7.5/CONSENSUS_ACTIVATION.md`:
- Consensus activation guide
- Security review findings addressed
- Testnet soak test results
- Mainnet activation checklist

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.5 — Consensus Activation
**Agent**: Agent B (Apps & Infrastructure)
