# v0.10.14 — Legacy Code & Stub Elimination

**Last Updated**: 2026-07-14
**Version**: 1.0 — Legacy Code & Stub Elimination

**Release Theme**: Eliminate duplicate/legacy code paths and remove or gate incomplete stub implementations that are currently exposed as production endpoints. Focus on security-critical bypasses (FHE, orchestration simulation), correctness-critical fake implementations (settlement, key rotation, transaction status), and architectural debt (shadow packages, deprecated routers, duplicate implementations).

**Goal**: Remove or properly gate all fake/incomplete implementations that are currently active in production paths, and consolidate duplicate stacks to a single canonical implementation per domain.

> **Scope**: 14 focus tasks split across Agent A (shared core cleanup) and Agent B (apps, CLI, legacy removal). No new user-facing features; all work is cleanup and hardening.
> **Prerequisites**: [v0.10.13](../v0.10.13/change.log) (✅ complete).
> **Risk**: High. Several tasks remove active endpoints or change previously permissive behavior (disabling fake FHE, gating orchestration, removing legacy routers). Document breaking changes in release notes.

---

## Task Split Overview

| Agent | Domain | Tasks | Focus |
|-------|--------|-------|-------|
| **Agent A** | Shared core cleanup (`aitbc/`, `cli/`) | 4 | CLI shadow package, agent registry duplication, shared bridge/identity consolidation |
| **Agent B** | Apps & legacy removal (`apps/`) | 10 | FHE bypass, orchestration simulation, settlement, key rotation, transaction status, pool-hub legacy, governance duplicates, service registry, coordinator factories |

**Conflict boundary**: Agent A owns `aitbc/` and `cli/`. Agent B owns `apps/`. The shared `aitbc.agent_bridge` and `aitbc.bridge` packages are touched by both — sequence through coordination log. Agent B owns all app-level routers and services.

---

## Agent A — Shared Core Cleanup

**Scope**: Remove duplicate/legacy implementations in shared core and CLI that shadow canonical packages.

**Working directory**: `/opt/aitbc/`

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ cli/
cd /opt/aitbc && ./venv/bin/python -m ruff check aitbc/ cli/
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/cli -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Remove CLI `aitbc` shadow package | 🔴 P0 | `cli/aitbc/`, `cli/setup.py`, `pyproject.toml` | ✅ |
| A2 | Resolve agent registry duplication | 🟡 P1 | `aitbc/agent_registry/`, `apps/agent-coordinator/src/agent_app/routing/agent_discovery.py`, `aitbc/agent_bridge/src/integration_layer.py` | ✅ |
| A3 | Consolidate shared bridge implementations | 🟡 P1 | `aitbc/bridge/`, `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/services/cross_chain/bridge_enhanced.py`, `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/services/cross_chain/bridge_client_adapter.py` | ✅ |
| A4 | Consolidate shared agent identity/wallet types | 🟡 P1 | `aitbc/agent_identity/`, `apps/coordinator-api/src/coordinator_api/agent_identity/` | ✅ |

### Agent A — Detailed Instructions

#### A1: Remove CLI `aitbc` shadow package

**Problem**: `cli/aitbc/` defines a minimal `AITBCHTTPClient`, exceptions, and constants that shadow the canonical `aitbc/` package. The project's mypy configuration acknowledges this shadowing. Installing the CLI can include this shadow package, causing incorrect imports.

**Fix**:
- Delete `cli/aitbc/` directory entirely.
- Update `cli/setup.py` to explicitly exclude the shadow package (use `packages=find_packages(exclude=["aitbc"])` or list packages explicitly).
- Update `cli/` imports to use the canonical `aitbc` package from the root.
- Remove the mypy shadowing workaround from `pyproject.toml`.
- Verify CLI imports work with the canonical package.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -c "import sys; sys.path.insert(0, 'cli'); from aitbc import AITBCHTTPClient; print('canonical import ok')"
cd /opt/aitbc/cli && ../venv/bin/python -c "from aitbc import AITBCHTTPClient; print('cli import ok')"
cd /opt/aitbc && ./venv/bin/python -m pytest tests/cli -q -o addopts=""
```

---

#### A2: Resolve agent registry duplication

**Problem**: Two agent registry implementations exist:
- Standalone FastAPI/SQLite service in `aitbc/agent_registry/src/app.py`
- In-process Redis-backed registry in `apps/agent-coordinator/src/agent_app/routing/agent_discovery.py`

The shared `aitbc.agent_bridge` points to an undeployed `localhost:8013` registry service, causing connection failures.

**Fix**:
- Choose one implementation as canonical (recommend the Redis-backed in-process registry for now).
- If standalone service is canonical: deploy it, update `aitbc.agent_bridge` endpoints, delete the in-process registry.
- If in-process registry is canonical: delete `aitbc/agent_registry/` standalone service, update `aitbc.agent_bridge` to use coordinator API endpoints, remove stale `localhost:8013` references.
- Update documentation to reflect the chosen architecture.

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts="" -k agent_registry
cd /opt/aitbc && ./venv/bin/python -c "from aitbc.agent_bridge import AgentBridgeClient; print('bridge client ok')"
```

---

#### A3: Consolidate shared bridge implementations

**Problem**: Multiple bridge implementations exist:
- Canonical `aitbc.bridge.BridgeClient` in shared core
- Deprecated `bridge_enhanced.py` in coordinator-api (explicitly marked as superseded by `BridgeClientAdapter`)
- `BridgeClientAdapter` wrapping the canonical client

The coordinator-api cross-chain router still imports and instantiates the deprecated `bridge_enhanced.py`.

**Fix**:
- Ensure `BridgeClientAdapter` is the only bridge abstraction used in coordinator-api.
- Delete or reduce `bridge_enhanced.py` to only the necessary SQLModel persistence layer if still needed.
- Update `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/routers/cross_chain_integration.py` to use `BridgeClientAdapter` exclusively.
- Remove deprecation comments once migration is complete.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k bridge
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/coordinator-api/src/coordinator_api/contexts/cross_chain/
```

---

#### A4: Consolidate shared agent identity/wallet types

**Problem**: Two agent identity/wallet stacks exist:
- Flat `coordinator_api.agent_identity` package with legacy `wallet_adapter.py` (returns fake data)
- Enhanced `wallet_adapter_enhanced.py` with actual RPC operations

The bounded-context agent identity router imports the old flat package, which uses the legacy fake adapter.

**Fix**:
- Select one wallet abstraction as canonical (recommend the enhanced adapter).
- Migrate the agent identity manager into the bounded context (`contexts/agent_identity/`).
- Remove the legacy fake adapter `wallet_adapter.py`.
- Ensure all wallet operations use the enhanced adapter with real RPC calls.
- Update imports to use the canonical location.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k wallet
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/coordinator-api/src/coordinator_api/contexts/agent_identity/
```

---

## Agent B — Apps & Legacy Removal

**Scope**: Remove or gate fake/incomplete implementations in apps, delete legacy routers, and consolidate duplicate implementations.

**Working directory**: `/opt/aitbc/`

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Disable ML-ZK FHE route bypass | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/contexts/zk_applications/routers/ml_zk_proofs.py`, `apps/coordinator-api/src/coordinator_api/main.py` | ✅ |
| B2 | Gate or disable simulated orchestration | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/services/orchestrator_service.py`, `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_router.py` | ✅ |
| B3 | Disable settlement until implementation is complete | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/contexts/settlement/routers/settlement.py`, `apps/coordinator-api/src/coordinator_api/settlement/manager.py`, `apps/coordinator-api/src/coordinator_api/settlement/bridges/` | ✅ |
| B4 | Fix key rotation to actually re-encrypt | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/security/services/key_management.py`, `apps/coordinator-api/src/coordinator_api/contexts/confidential/routers/confidential.py` | ✅ |
| B5 | Fix transaction status duplicate method | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/cross_chain/services/multi_chain_transaction_manager.py` | ✅ |
| B6 | Implement or disable Ollama task stub | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` | ✅ |
| B7 | Remove pool-hub legacy router | 🟡 P1 | `apps/pool-hub/src/poolhub_legacy/`, `apps/pool-hub/src/poolhub/app/main.py` | ✅ |
| B8 | Consolidate governance implementations | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/governance.py`, `governance_flat.py`, `governance_enhanced.py`, `apps/coordinator-api/src/coordinator_api/main.py` | ✅ |
| B9 | Wire or remove deprecated service registry | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/services.py`, `apps/coordinator-api/src/coordinator_api/models/registry.py` | ✅ |
| B10 | Remove duplicate coordinator app factory | 🟢 P2 | `apps/coordinator-api/src/coordinator_api/core/app.py`, `apps/coordinator-api/src/coordinator_api/core/__init__.py` | ✅ |

### Agent B — Detailed Instructions

#### B1: Disable ML-ZK FHE route bypass

**Problem**: The normal FHE router (`/v1/fhe`) is correctly disabled and returns `501`. However, a separate active route `/v1/ml-zk/fhe/inference` bypasses this protection, has no auth dependency, and uses `MockFHEProvider` which serializes plaintext JSON instead of encrypting it.

**Fix**:
- Remove the `/v1/ml-zk/fhe/inference` route from `ml_zk_proofs.py`.
- Alternatively, add the same authentication dependency as `/v1/fhe` and require a vetted FHE provider (not the mock).
- If removing, also remove the route mount from `main.py`.
- Update the bounded-context README to reflect that FHE is fully disabled until a vetted library is integrated.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -c "from coordinator_api.main import app; print([r.path for r in app.routes])" | grep -v "ml-zk/fhe"
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k fhe
```

---

#### B2: Gate or disable simulated orchestration

**Problem**: The workflow endpoint actively executes workflows but the implementation is a simulator:
- ZK verification falls back to ordinary checks with a TODO for SNARK/STARK integration
- Inference returns `"simulated_result"`
- Training returns fake loss and `"model_updated": True`
- Data-processing and custom steps return fabricated counts/results

**Fix**:
- Add a feature flag `ENABLE_ORCHESTRATION_SIMULATION` defaulting to `false`.
- When disabled, return `501 Not Implemented` for workflow execution endpoints.
- Document in the bounded-context README that orchestration is not production-ready.
- Alternatively, implement real ZK verification and actual task execution before removing the simulation flag.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k orchestrator
# Test that disabled flag returns 501
```

---

#### B3: Disable settlement until implementation is complete

**Problem**: The settlement bounded-context README explicitly identifies it as a stub. The active router:
- Uses module-level in-memory storage
- Creates a new `BridgeManager` for every request
- Does not initialize any bridge adapter
- Background settlement processing marks records failed with `"No bridges configured"`
- Base bridge signature verification unconditionally returns `True`
- LayerZero target addresses and signer addresses are `"0x..."` placeholders

**Fix**:
- Remove the settlement router mount from `main.py` or return `501` for all settlement endpoints.
- Delete the in-memory storage and per-request `BridgeManager` creation.
- Implement proper bridge initialization, signature verification, and provider configuration before re-enabling.
- Add real persistence layer instead of module-level storage.
- Remove placeholder addresses and implement actual signing.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -c "from coordinator_api.main import app; print([r.path for r in app.routes])" | grep -v "settlement"
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k settlement
```

---

#### B4: Fix key rotation to actually re-encrypt

**Problem**: `rotate_keys()` calls `_reencrypt_transactions()`, but that method only logs `"Would re-encrypt transactions"` and executes `pass`. The HTTP endpoint returns a successful new version without actually re-encrypting any records.

**Fix**:
- Implement `_reencrypt_transactions()` to actually re-encrypt all affected transaction records with the new key.
- Make the rotation transactional — if re-encryption fails, roll back the key version.
- Add proper error handling and logging.
- If implementation is not ready, return `501 Not Implemented` instead of reporting successful rotation.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k key_rotation
# Test that rotation actually re-encrypts data
```

---

#### B5: Fix transaction status duplicate method

**Problem**: `get_transaction_status()` calls `_update_transaction_status()`, which is empty (`pass`). A separate `_update_transaction_status_v2()` exists with the actual implementation, but the caller does not use it.

**Fix**:
- Replace the old `_update_transaction_status()` with the v2 implementation.
- Delete the duplicate `_update_transaction_status_v2()` method.
- Update all callers to use the unified method.
- Add tests to verify transaction status updates work correctly.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k transaction_status
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/coordinator-api/src/coordinator_api/contexts/cross_chain/services/multi_chain_transaction_manager.py
```

---

#### B6: Implement or disable Ollama task stub

**Problem**: The GPU marketplace router mounts `/tasks/ollama`, but the handler only validates booking and returns a generated task ID plus the request payload. It does not submit or persist a task. The route has no authentication.

**Fix**:
- Implement real queue/job dispatch for Ollama tasks with persistence.
- Add authentication to the route.
- If implementation is not ready, return `501 Not Implemented` or remove the route entirely.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k ollama
# Test that tasks are actually queued and persisted
```

---

#### B7: Remove pool-hub legacy router

**Problem**: The `poolhub_legacy` package is explicitly marked as deprecated since v0.6.7, with `poolhub/` being the canonical implementation. Despite this, the active application imports and mounts the legacy pools router. The legacy registry uses in-memory dictionaries, while the canonical implementation has SQLAlchemy models and PostgreSQL/Redis-backed repositories.

**Fix**:
- Remove the import and mount of `poolhub_legacy.routers.pools` from `poolhub/app/main.py`.
- Delete the entire `poolhub_legacy/` directory.
- Ensure all pool/miner/job operations use the canonical repositories.
- Update documentation to reflect that the legacy implementation is removed.

**Verification**:
```bash
cd /opt/aitbc/apps/pool-hub && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/pool-hub/src/poolhub/
```

---

#### B8: Consolidate governance implementations

**Problem**: Three governance routers exist:
- `governance.py` with `/governance` (SQLModel-backed)
- `governance_flat.py` with `/governance` (in-memory service)
- `governance_enhanced.py` with `/governance-enhanced`

The main application mounts `governance_flat` and `governance_enhanced`, while `governance.py` is imported but not mounted. This causes confusion and potential conflicts.

**Fix**:
- Keep the database-backed implementation (`governance.py`) as canonical.
- Remove the in-memory flat implementation (`governance_flat.py`).
- Standardize route names and auth across implementations.
- Decide whether to keep `/governance-enhanced` as a separate v2 API or merge it into the canonical router.
- Update `main.py` to mount only the canonical router(s).

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k governance
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/coordinator-api/src/coordinator_api/contexts/governance/
```

---

#### B9: Wire or remove deprecated service registry

**Problem**: A real service registry model and predefined service catalog exist, but the active legacy service router creates `MockServiceRegistry.get_service()`, which always returns `None`. The endpoint itself says it is deprecated and should use `/v1/registry/services/{service_id}`, but no corresponding production registry router is wired.

**Fix**:
- Either wire the real registry with a proper router implementation, or
- Remove the deprecated endpoint and its dead models entirely.
- If keeping the registry, implement the missing `/v1/registry/services/{service_id}` router.
- Update documentation to reflect the decision.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts="" -k registry
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/coordinator-api/src/coordinator_api/contexts/infrastructure/
```

---

#### B10: Remove duplicate coordinator app factory

**Problem**: Two coordinator application factories exist:
- Canonical in `coordinator_api.main.py` (entry point for uvicorn)
- Duplicate in `coordinator_api/core/app.py` with its own middleware and router registration stack

The second stack is only referenced internally by `coordinator_api.core`, not by the deployed service.

**Fix**:
- Remove the unused factory stack from `core/app.py`.
- Alternatively, convert it into a thin re-export of `main.create_app` if needed for internal imports.
- Update `core/__init__.py` to not reference the duplicate factory.

**Verification**:
```bash
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -c "from coordinator_api.main import app; print('main app ok')"
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/coordinator-api/src/coordinator_api/core/
```

---

## Coordination Protocol

When both agents need to touch shared files or adjacent code paths, follow this protocol:

1. **Declare intent**: Before starting work on a shared file, the agent posts in this `AGENTS.md` (under a "Coordination" section) which file(s) they intend to modify and when.
2. **Sequence, don't parallelize**: Shared files are edited sequentially, not concurrently. Agent A goes first for `aitbc/` shared files; Agent B goes first for `apps/` shared files.
3. **Lock files during editing**: The agent currently editing a shared file adds a `# WIP: Agent X` comment at the top of the file while editing. The other agent waits until the comment is removed.
4. **Shared files list** (must be sequenced):
   - `aitbc/agent_bridge/` — Agent A owns types, Agent B owns implementations
   - `aitbc/bridge/` — Agent A owns canonical client, Agent B owns coordinator-api adapters
   - `aitbc/agent_registry/` — Agent A owns, but Agent B touches for coordinator integration
5. **Conflict resolution**: If both agents edit the same file despite the protocol, the agent whose domain owns the file wins. The other agent rebases.

---

## Acceptance Criteria

### Agent A
- [x] CLI `aitbc` shadow package removed; all CLI imports use canonical `aitbc/`
- [x] Agent registry consolidation complete; no duplicate implementations remain
- [x] Bridge implementations consolidated; only `BridgeClientAdapter` used in coordinator-api
- [x] Agent identity/wallet stacks consolidated; only enhanced adapter with real RPC calls
- [x] All tests pass: `mypy aitbc/ cli/`, `ruff check aitbc/ cli/`, `pytest tests/unit tests/cli`

### Agent B
- [x] ML-ZK FHE route bypass removed or properly authenticated with real provider
- [x] Orchestration simulation gated behind feature flag or disabled
- [x] Settlement endpoints disabled until implementation is complete
- [x] Key rotation actually re-encrypts transactions or returns 501
- [x] Transaction status duplicate method removed; v2 implementation active
- [x] Ollama task stub implemented with real dispatch or disabled
- [x] Pool-hub legacy router removed; canonical repositories used
- [x] Governance implementations consolidated; single canonical router
- [x] Service registry either wired with real implementation or removed
- [x] Duplicate coordinator app factory removed
- [x] All tests pass: `ruff check apps/`, `pytest apps/coordinator-api/tests tests/unit`

### Release Notes
- [x] Document all breaking changes (disabled endpoints, removed legacy routers)
- [x] Update `docs/releases/README.md` to mark v0.10.14 as in progress
- [x] Update root `AGENTS.md` to set v0.10.14 as current in-flight plan
- [x] Create `docs/releases/v0.10.14/change.log` with summary of changes

---

## Coordination Log

*Use this section to declare intent and sequence shared file edits.*

*(No coordination entries yet)*
