# v0.7.4 Deferred v0.7.x Items — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Deferred v0.7.x Items — External Oracle, Cross-Chain Governance, Parameter Automation, Emergency Proposals, Coordinator-API Bridge Integration, MultiValidatorPoA Activation

**Goal**: Implement the 7 items deferred from v0.7.0-v0.7.3 that were tagged "deferred to v0.8.x" but never assigned to a specific release. These are bridge/governance/consensus items that belong in the v0.7.x track.

> **Not on the critical path**: v0.8.x (trading) and v0.9.0 (atomic settlement) do not depend on v0.7.4. This release can ship in parallel with v0.8.x work.

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅ (Agent A `9a7b17a34`), [v0.7.3](../v0.7.3/change.log) (Agent A ✅ `923e0a5bc`).

> **Risk**: Medium-High. MultiValidatorPoA activation is consensus-critical (requires security review). External oracle adds external dependency. Cross-chain governance touches the bridge path. Low-risk items: parameter automation, emergency proposals.

> **Consider phasing**: Low-risk items (parameter automation, emergency proposals) can ship first. High-risk items (MultiValidatorPoA, external oracle) need security review and can ship later.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (ExternalOracleClient, oracle fallback, cross-chain governance)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (oracle config, governance endpoints, parameter APIs, MultiValidatorPoA)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [ExternalOracleClient](./agent-a.md#a1-externaloracleclient)
- [Oracle Fallback Policy](./agent-a.md#a2-oracle-fallback-policy)
- [Cross-Chain Governance Utilities](./agent-a.md#a3-cross-chain-governance-utilities)
- [Parameter Change Execution](./agent-a.md#a4-parameter-change-execution)
- [Unit Tests](./agent-a.md#a5-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Oracle Config](./agent-b.md#b1-oracle-config)
- [Cross-Chain Governance Endpoints](./agent-b.md#b2-cross-chain-governance-endpoints)
- [Pool-Hub Parameter API](./agent-b.md#b3-pool-hub-parameter-api)
- [Marketplace Parameter API](./agent-b.md#b4-marketplace-parameter-api)
- [Emergency Proposal Handling](./agent-b.md#b5-emergency-proposal-handling)
- [Coordinator-API Bridge Integration](./agent-b.md#b6-integrate-coordinator-api-with-bridgeclient)
- [MultiValidatorPoA Activation](./agent-b.md#b7-multivalidatorpoa-activation--deferred-to-v075)
- [CLI Commands](./agent-b.md#b8-add-cli-commands)
- [Integration Tests](./agent-b.md#b9-integration-tests)

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

1. ✅ **In-process bridge verification** (v0.7.2) — `InProcessVerifier` works (note: blockchain-node uses inline verification logic, not the shared SDK's `InProcessVerifier` directly — see A1/A2 for integration)
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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.4 — Deferred v0.7.x Items
