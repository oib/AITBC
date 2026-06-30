# v0.7.4 Deferred v0.7.x Items — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add oracle config, cross-chain governance endpoints, parameter automation APIs, emergency proposal handling, coordinator-api bridge integration, MultiValidatorPoA activation, CLI commands, and tests.

**Working directory**: `/opt/aitbc/apps/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A4 complete. v0.7.3 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/governance/src/ apps/pool-hub/src/ apps/blockchain-node/src/aitbc_chain/consensus/ cli/aitbc_cli/commands/governance.py
cd /opt/aitbc && PYTHONPATH=apps/governance/src:aitbc ./venv/bin/python -m pytest apps/governance/tests/test_v074_deferred.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add `BRIDGE_ORACLE_ENDPOINTS` config to blockchain-node Settings | Medium | `apps/blockchain-node/src/aitbc_chain/config.py` (extend) | ✅ |
| B2 | Add cross-chain governance endpoints to governance service | 🔴 P0 | `apps/governance/src/governance_service/main.py` (extend) | ✅ |
| B3 | Add governance-triggered parameter change API to pool-hub | Medium | `apps/pool-hub/src/poolhub/app/routers/services.py` (extend) | ✅ |
| B4 | Add governance-triggered parameter change API to marketplace | Medium | `apps/marketplace/src/marketplace_service/` (extend) | ✅ |
| B5 | Add emergency proposal handling — accelerated timelock, fast-track execution | Medium | `apps/governance/src/governance_service/services/governance_service.py` (extend) | ✅ |
| B6 | Integrate coordinator-api with BridgeClient — replace CrossChainBridgeService | Medium | `apps/coordinator-api/src/app/contexts/cross_chain/` (refactor) | ✅ |
| B7 | MultiValidatorPoA activation — security review, remove guard, enable | ⛔ DEFERRED to v0.7.5 | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ⛔ Deferred |
| B8 | Add CLI commands — governance propagate, aggregate-votes, bridge oracle-status, consensus validators/status | Medium | `cli/aitbc_cli/commands/governance.py` (extend), `cli/aitbc_cli/commands/bridge.py` (extend), `cli/aitbc_cli/commands/chain.py` (extend) | ✅ |
| B9 | Integration tests | High | `apps/governance/tests/test_v074_deferred.py` (new) | ✅ |

---

## B1: Oracle Config

Add to `apps/blockchain-node/src/aitbc_chain/config.py`:
```python
bridge_oracle_endpoints: list[str] = []  # External oracle endpoints
bridge_verification_mode: str = "in_process"  # "in_process" or "oracle"
bridge_oracle_health_check_interval: int = 60  # seconds
```

---

## B2: Cross-Chain Governance Endpoints

Add to `apps/governance/src/governance_service/main.py`:
- `POST /v1/governance/proposals/{id}/propagate` — propagate proposal to all chains
- `POST /v1/governance/proposals/{id}/aggregate-votes` — aggregate votes from all chains
- `POST /v1/governance/proposals/{id}/execute-cross-chain` — execute on all chains

Use Agent A's `propagate_proposal()`, `aggregate_votes()`, `execute_cross_chain()` from A3.

---

## B3: Pool-Hub Parameter API

Add governance-triggered parameter change endpoint to pool-hub:
- `POST /v1/poolhub/parameters/apply` — apply governance-approved parameter change
- Validate: parameter change must have approved proposal ID
- Apply: update service config based on ParameterChangeSchema

---

## B4: Marketplace Parameter API

Add governance-triggered parameter change endpoint to marketplace:
- `POST /v1/marketplace/parameters/apply` — apply governance-approved parameter change
- Similar validation and apply logic as pool-hub

---

## B5: Emergency Proposal Handling

Add to `apps/governance/src/governance_service/services/governance_service.py`:
- Detect emergency proposal type (`ProposalType.EMERGENCY`)
- Apply accelerated timelock (e.g., 1 hour instead of 24 hours)
- Fast-track execution — skip additional checks for emergency proposals
- Log emergency proposal handling for audit

---

## B6: Coordinator-API Bridge Integration

Refactor `apps/coordinator-api/src/app/contexts/cross_chain/`:
- Replace `CrossChainBridgeService` with `BridgeClient` from `aitbc.bridge.client`
- Remove duplicate bridge service code
- Update all cross-chain operations to use `BridgeClient`
- Verify coordinator-api cross-chain functionality works with shared SDK

---

## B7: MultiValidatorPoA Activation (DEFERRED to v0.7.5)

- **DEFERRED**: Requires security review before activation
- Security review findings documented in `docs/releases/v0.7.4/security-review-multivalidator-poa.md`
- Remove `RuntimeError("MultiValidatorPoA is not yet activated")` guard
- Enable via config flag: `consensus_mode: str = "multi_validator_poa"`
- Coordinate with PBFT activation

---

## B8: CLI Commands

Extend `cli/aitbc_cli/commands/governance.py`:
- `aitbc governance propagate <proposal_id>` — propagate proposal to all chains
- `aitbc governance aggregate-votes <proposal_id>` — aggregate votes from all chains

Extend `cli/aitbc_cli/commands/bridge.py`:
- `aitbc bridge oracle-status` — check external oracle health

Extend `cli/aitbc_cli/commands/chain.py`:
- `aitbc chain validators` — list active validators
- `aitbc chain consensus-status` — show consensus mode and status

---

## B9: Integration Tests

`apps/governance/tests/test_v074_deferred.py` — tests for:
- Cross-chain governance endpoints
- Parameter change APIs (pool-hub, marketplace)
- Emergency proposal handling
- Coordinator-api bridge integration
- CLI commands

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.4 — Deferred v0.7.x Items
**Agent**: Agent B (Apps & Infrastructure)
