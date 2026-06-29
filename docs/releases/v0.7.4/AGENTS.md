# v0.7.4 — Agent Task Assignment

**Release Theme**: Deferred v0.7.x Items — External Oracle, Cross-Chain Governance, Parameter Automation, Emergency Proposals, Coordinator-API Bridge Integration, MultiValidatorPoA Activation

**Goal**: Implement the 7 items deferred from v0.7.0-v0.7.3 that were tagged "deferred to v0.8.x" but never assigned to a specific release. These are bridge/governance/consensus items that belong in the v0.7.x track.

> **Not on the critical path**: v0.8.x (trading) and v0.9.0 (atomic settlement) do not depend on v0.7.4. This release can ship in parallel with v0.8.x work.

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅ (Agent A `9a7b17a34`), [v0.7.3](../v0.7.3/change.log) (Agent A ✅ `923e0a5bc`).

> **Risk**: Medium-High. MultiValidatorPoA activation is consensus-critical (requires security review). External oracle adds external dependency. Cross-chain governance touches the bridge path. Low-risk items: parameter automation, emergency proposals.

> **Consider phasing**: Low-risk items (parameter automation, emergency proposals) can ship first. High-risk items (MultiValidatorPoA, external oracle) need security review and can ship later.

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.7.4 Target |
|-----------|----------|---------------|---------------|
| **ExternalOracleClient** | `aitbc/bridge/oracle.py:228-262` | STUB — all methods raise `NotImplementedError` | Implement with external oracle API calls + fallback |
| **BRIDGE_ORACLE_ENDPOINTS config** | — | ❌ NONE — only in v0.7.2 change.log:111 | Add to blockchain-node Settings |
| **Oracle fallback policy** | — | ❌ NONE — 0 matches for fallback terms | Implement in-process → oracle → in-process fallback |
| **Oracle roadmap doc** | — | ❌ NONE — `docs/architecture/oracle-roadmap.md` doesn't exist | Create |
| **Cross-chain governance** | `aitbc/governance/` | ❌ NONE — single-chain only | Add proposal propagation, vote aggregation, cross-chain execution |
| **ParameterChangeSchema** | `aitbc/governance/types.py:119-136` | PARTIAL — dataclass only, no execute method | Add `apply_parameter_change()` to governance service |
| **Pool-hub parameter API** | `apps/pool-hub/src/poolhub/app/routers/services.py:54-127` | EXISTS but manual, not governance-driven | Add governance-triggered parameter change endpoint |
| **Marketplace parameter API** | — | ❌ NONE | Add governance-triggered parameter change endpoint |
| **Emergency proposals** | `aitbc/governance/types.py:41`, `main.py:221` | PARTIAL — type + quorum config exist, no special handling | Add accelerated timelock + fast-track execution |
| **Coordinator-API bridge** | `apps/coordinator-api/src/app/contexts/cross_chain/` | PARTIAL — has own CrossChainBridgeService, not BridgeClient | Replace with BridgeClient, remove duplicate |
| **MultiValidatorPoA** | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (294 lines) | STUB — fully implemented but dead code, RuntimeError guard | Security review → activate |
| **PBFT** | `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` | STUB — dead code, depends on MultiValidatorPoA | Activate with MultiValidatorPoA |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **In-process bridge verification** (v0.7.2) — `InProcessOracleClient` works, used as fallback
2. ✅ **Governance SDK** (v0.7.3 Agent A) — types, client, onchain utilities exist
3. ✅ **Governance service** (v0.7.3) — 991 lines, FastAPI, domain models, service layer
4. ✅ **ParameterChangeSchema** — dataclass exists, just needs execution logic
5. ✅ **Emergency proposal type** — `EMERGENCY = "emergency"` in ProposalType enum
6. ✅ **Emergency quorum config** — `emergency_quorum_threshold: 0.8` in main.py:221
7. ✅ **MultiValidatorPoA implementation** — 294 lines, fully implemented, just gated
8. ✅ **PBFT implementation** — depends on MultiValidatorPoA, also fully implemented
9. ✅ **Coordinator-api cross-chain context** — exists, just needs BridgeClient integration
10. ✅ **Pool-hub service config router** — exists, just needs governance-triggered endpoint

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 5 items | `aitbc/bridge/oracle.py` (extend), `aitbc/governance/` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 7 items | `apps/governance/`, `apps/pool-hub/`, `apps/marketplace/`, `apps/coordinator-api/`, `apps/blockchain-node/`, `cli/` |

**Conflict boundary**: Agent A owns `aitbc/bridge/oracle.py` and `aitbc/governance/`. Agent B owns `apps/`, `cli/`. Agent B consumes Agent A's oracle client, governance types, and cross-chain governance utilities.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes relevant tasks. Low-risk items (parameter automation, emergency proposals) can proceed independently.

---

## Agent A — Shared Core

**Scope**: Implement ExternalOracleClient, oracle fallback policy, cross-chain governance utilities (propagation, aggregation, execution), and parameter change execution helpers.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅, v0.7.3 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ aitbc/governance/ && ./venv/bin/python -m ruff check aitbc/bridge/ aitbc/governance/ tests/unit/test_v074_deferred.py && ./venv/bin/python -m pytest tests/unit/test_v074_deferred.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Implement `ExternalOracleClient` — replace NotImplementedError stubs with real oracle API calls | Medium | `aitbc/bridge/oracle.py` (extend) | ⬜ |
| A2 | Add oracle fallback policy — in-process → oracle → in-process fallback logic | Medium | `aitbc/bridge/oracle.py` (extend), `aitbc/bridge/proof.py` (extend) | ⬜ |
| A3 | Add cross-chain governance utilities — `propagate_proposal()`, `aggregate_votes()`, `execute_cross_chain()` | 🔴 P0 | `aitbc/governance/onchain.py` (extend), `aitbc/governance/client.py` (extend) | ⬜ |
| A4 | Add parameter change execution helper — `build_parameter_apply_tx()` | Medium | `aitbc/governance/onchain.py` (extend) | ⬜ |
| A5 | Unit tests for A1-A4 | High | `tests/unit/test_v074_deferred.py` (new) | ⬜ |

### Agent A — Detailed Instructions

#### A1: ExternalOracleClient

Extend `aitbc/bridge/oracle.py:228-262`:
- Replace `NotImplementedError` in `verify_proof()` with external oracle API call (httpx)
- Replace `NotImplementedError` in `check_finality()` with external oracle API call
- Add `__init__(endpoints: list[str], timeout: int = 30)` — takes oracle endpoints
- Add health check method: `is_healthy() -> bool`

#### A2: Oracle Fallback Policy

Add to `aitbc/bridge/oracle.py` or `aitbc/bridge/proof.py`:
- `OracleFallbackPolicy` class — manages oracle → in-process fallback
- `verify_with_fallback()` — try oracle first, fall back to in-process on failure
- Health check loop — periodically check oracle health
- Recovery — attempt oracle reconnection every 60s

#### A3: Cross-Chain Governance Utilities

Extend `aitbc/governance/onchain.py`:
- `build_proposal_propagation_tx(proposal_data, target_chain)` — bridge tx to propagate proposal
- `build_vote_aggregation_tx(votes, source_chain)` — bridge tx to aggregate votes

Extend `aitbc/governance/client.py`:
- `propagate_proposal(proposal_id, target_chains)` — propagate proposal to islands
- `aggregate_votes(proposal_id)` — aggregate votes from all chains
- `execute_cross_chain(proposal_id)` — execute on all chains after approval

#### A4: Parameter Change Execution

Extend `aitbc/governance/onchain.py`:
- `build_parameter_apply_tx(parameter_change)` — tx to apply parameter change to target service
- `validate_parameter_change(parameter_change, target_service_config)` — validate before applying

#### A5: Unit Tests

`tests/unit/test_v074_deferred.py` — tests for ExternalOracleClient (mocked httpx), fallback policy, cross-chain governance utilities, parameter change execution.

---

## Agent B — Apps & Infrastructure

**Scope**: Add oracle config, cross-chain governance endpoints, parameter automation APIs, emergency proposal handling, coordinator-api bridge integration, MultiValidatorPoA activation, CLI commands, and tests.

**Working directory**: `/opt/aitbc/apps/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A4 complete. v0.7.3 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/governance/src/ apps/pool-hub/src/ apps/blockchain-node/src/aitbc_chain/consensus/ cli/aitbc_cli/commands/governance.py
cd /opt/aitbc && PYTHONPATH=apps/governance/src:aitbc ./venv/bin/python -m pytest apps/governance/tests/test_v074_deferred.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add `BRIDGE_ORACLE_ENDPOINTS` config to blockchain-node Settings | Medium | `apps/blockchain-node/src/aitbc_chain/config.py` (extend) | ⬜ |
| B2 | Add cross-chain governance endpoints to governance service | 🔴 P0 | `apps/governance/src/governance_service/main.py` (extend) | ⬜ |
| B3 | Add governance-triggered parameter change API to pool-hub | Medium | `apps/pool-hub/src/poolhub/app/routers/services.py` (extend) | ⬜ |
| B4 | Add governance-triggered parameter change API to marketplace | Medium | `apps/marketplace/src/marketplace_service/` (extend) | ⬜ |
| B5 | Add emergency proposal handling — accelerated timelock, fast-track execution | Medium | `apps/governance/src/governance_service/services/governance_service.py` (extend) | ⬜ |
| B6 | Integrate coordinator-api with BridgeClient — replace CrossChainBridgeService | Medium | `apps/coordinator-api/src/app/contexts/cross_chain/` (refactor) | ⬜ |
| B7 | MultiValidatorPoA activation — security review, remove guard, enable | 🔴 P0 (gated) | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (extend) | ⬜ |
| B8 | Add CLI commands — governance propagate, aggregate-votes, bridge oracle-status, consensus validators/status | Medium | `cli/aitbc_cli/commands/governance.py` (extend), `cli/aitbc_cli/commands/bridge.py` (extend), `cli/aitbc_cli/commands/chain.py` (extend) | ⬜ |
| B9 | Integration tests | High | `apps/governance/tests/test_v074_deferred.py` (new) | ⬜ |

### Agent B — Detailed Instructions

#### B1: Oracle Config

Add to `apps/blockchain-node/src/aitbc_chain/config.py`:
```python
bridge_oracle_endpoints: list[str] = []  # External oracle endpoints
bridge_verification_mode: str = "in_process"  # "in_process" or "oracle"
bridge_oracle_health_check_interval: int = 60  # seconds
```

#### B2: Cross-Chain Governance Endpoints

Add to `apps/governance/src/governance_service/main.py`:
- `POST /v1/governance/proposals/{id}/propagate` — propagate proposal to all chains
- `POST /v1/governance/proposals/{id}/aggregate-votes` — aggregate votes from all chains
- `POST /v1/governance/proposals/{id}/execute-cross-chain` — execute on all chains

Use Agent A's `propagate_proposal()`, `aggregate_votes()`, `execute_cross_chain()` from A3.

#### B3: Pool-Hub Parameter API

Add governance-triggered parameter change endpoint to pool-hub:
- `POST /v1/poolhub/parameters/apply` — apply governance-approved parameter change
- Validate: parameter change must have approved proposal ID
- Apply: update service config based on ParameterChangeSchema

#### B4: Marketplace Parameter API

Add governance-triggered parameter change endpoint to marketplace:
- `POST /v1/marketplace/parameters/apply` — apply governance-approved parameter change

#### B5: Emergency Proposal Handling

Extend `apps/governance/src/governance_service/services/governance_service.py`:
- In `create_proposal()`: if type == EMERGENCY, set accelerated timelock (4h instead of 48h)
- In `execute_proposal()`: if type == EMERGENCY, enforce 80% quorum, allow fast-track execution
- Add `emergency_timelock_blocks` config (default: 7200 = 4h at 2s block time)

#### B6: Coordinator-API Bridge Integration

Refactor `apps/coordinator-api/src/app/contexts/cross_chain/`:
- Replace `CrossChainBridgeService` with `aitbc.bridge.BridgeClient`
- Route bridge requests through blockchain-node bridge RPC
- Remove duplicate bridge implementation
- Update tests to use BridgeClient mocks

#### B7: MultiValidatorPoA Activation

⚠️ **Requires security review sign-off before activation.**

- Security audit of `multi_validator_poa.py` (294 lines) and `pbft.py`
- Remove `RuntimeError` guard at line 45-49
- Enable `MULTI_VALIDATOR_CONSENSUS_ENABLED=true` in production config
- Add consensus validator metrics
- Add rollback plan (disable if issues found)
- Test on testnet first

#### B8: CLI Commands

Add to `cli/aitbc_cli/commands/governance.py`:
- `aitbc governance propagate --proposal-id <id>` — propagate proposal
- `aitbc governance aggregate-votes --proposal-id <id>` — aggregate votes

Add to `cli/aitbc_cli/commands/bridge.py`:
- `aitbc bridge oracle-status` — oracle health + fallback status

Add to `cli/aitbc_cli/commands/chain.py`:
- `aitbc consensus validators` — list active validators
- `aitbc consensus status` — show consensus mode

#### B9: Integration Tests

`apps/governance/tests/test_v074_deferred.py` — tests for:
- Cross-chain proposal propagation
- Vote aggregation
- Parameter automation (pool-hub + marketplace)
- Emergency proposal handling
- Oracle fallback
- CLI commands (smoke tests)

---

## Coordination

### Shared Files

Agent A owns `aitbc/bridge/oracle.py`, `aitbc/governance/`. Agent B owns `apps/`, `cli/`. No shared files.

### Sequencing

1. **Phase 1** (low-risk, parallel): Agent A A4 (parameter helper), Agent B B3-B5 (parameter APIs, emergency proposals)
2. **Phase 2** (Agent A first): Agent A A1-A2 (oracle), A3 (cross-chain governance), Agent B B1-B2 (oracle config, cross-chain endpoints)
3. **Phase 3** (Agent B): B6 (coordinator-api), B7 (MultiValidatorPoA — gated on security review), B8 (CLI), B9 (tests)

### Dependencies

```
v0.7.2 (bridge verification) ✅
v0.7.3 (governance SDK) ✅ Agent A
    │
    ├── A1 (ExternalOracleClient) ──┐
    ├── A2 (oracle fallback) ───────┤
    ├── A3 (cross-chain gov) ───────┤
    ├── A4 (parameter helper) ──────┤
    │                                ├── A5 (tests)
    │                                │
    ├── B1 (oracle config) ─────────┐│
    ├── B2 (cross-chain endpoints) ─┤├── needs A3
    ├── B3 (pool-hub param API) ────┤├── needs A4
    ├── B4 (marketplace param API) ─┤├── needs A4
    ├── B5 (emergency proposals) ───┤│
    ├── B6 (coordinator-api) ───────┤│
    ├── B7 (MultiValidatorPoA) ─────┤│  ⚠️ gated on security review
    ├── B8 (CLI) ───────────────────┤│  needs A1-A3
    └── B9 (tests) ─────────────────┘│
```

### Phasing Recommendation

**Phase 1 (low-risk, ship first)**:
- A4: Parameter change execution helper
- B3: Pool-hub parameter API
- B4: Marketplace parameter API
- B5: Emergency proposal handling

**Phase 2 (medium-risk)**:
- A3: Cross-chain governance utilities
- B2: Cross-chain governance endpoints
- B8: CLI commands (governance propagate, aggregate-votes)

**Phase 3 (higher-risk, ship later)**:
- A1-A2: External oracle + fallback policy
- B1: Oracle config
- B6: Coordinator-api bridge integration

**Phase 4 (highest-risk, gated on security review)**:
- B7: MultiValidatorPoA activation
