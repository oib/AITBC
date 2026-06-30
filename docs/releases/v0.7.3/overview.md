# v0.7.3 Governance — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Governance — On-Chain Proposals, Voting, Parameter Changes (Same-Chain)

**Goal**: Wire the existing governance service (991 lines, `apps/governance/src/`) to the blockchain so proposals and votes are on-chain transactions. Replace local-only voting power with on-chain AIT balance snapshots. Add governance transaction types to blockchain-node. Defer cross-chain governance to v0.8.x (requires v0.7.2 verification + v0.7.1 multi-sig).

> **Rescope from original change.log**: The original v0.7.3 change.log bundled on-chain proposals + voting + parameter automation + cross-chain governance into one release. Cross-chain governance requires v0.7.2 bridge verification (in-process Merkle proofs) to be operational and tested, plus v0.7.1 multi-sig for secure proposal propagation. v0.7.2 Agent B is still in progress. Per the release-planning analysis, v0.7.3 is now scoped to **same-chain governance only**:
> - ✅ v0.7.3: On-chain proposals/votes (GOVERNANCE_PROPOSE/VOTE/EXECUTE tx types), on-chain balance snapshot for voting power, parameter change schema, timelock execution, CLI
> - ➡️ v0.8.x: Cross-chain governance (proposal propagation via bridge, cross-chain vote aggregation) — deferred until v0.7.2 verification is operational and audited
> - ➡️ v0.8.x: Parameter automation (pool-hub/marketplace parameter APIs) — deferred until target services expose parameter change endpoints

> **Stale claim correction**: The original analysis claimed "Pool Hub doesn't exist yet (confirmed in v0.6.7 investigation)". This is **WRONG** — v0.6.7 is complete (commit `5bb3803bd`). Pool Hub exists at `apps/pool-hub/` with `PoolHubBlockchainClient`, `Settings` (blockchain_rpc_url=8202, default_chain_id="ait-hub"), miner registration, and reward distribution. However, Pool Hub does NOT yet expose a parameter change API — that's a v0.8.x prerequisite for parameter automation.

> **Stale port correction**: The change.log migration guide references `BLOCKCHAIN_RPC_URL=http://localhost:8006`. Port 8006 is stale — the correct port is **8202** (verified in `apps/pool-hub/src/poolhub/settings.py:57` and `aitbc/constants.py:50`).

> **No external security audit**: All development is in-house (same as v0.7.1, v0.7.2).

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅ (Agent A `1fcf1e829` + Agent B `a4ea61295`), [v0.7.2](../v0.7.2/change.log) (Agent A ✅ `9a7b17a34`, Agent B 🔴 in progress), [v0.6.7](../v0.6.7/change.log) ✅ (`5bb3803bd`), [v0.5.16](../v0.5.16/change.log) ✅.

> **Risk**: Medium. Same-chain governance is self-contained — no bridge dependency. The main risk is adding new transaction types to blockchain-node (consensus-critical path). The existing tx processing in `poa.py:348` already handles arbitrary `type` strings in `tx.content`, so GOVERNANCE_* types are additive (new payload handling, not new consensus logic).

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (governance types, client, on-chain utilities)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (governance service config, blockchain tx types, CLI)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Governance types](./agent-a.md#a1-governance-types)
- [Governance client](./agent-a.md#a2-governance-client)
- [On-chain utilities](./agent-a.md#a3-on-chain-utilities)
- [Unit tests](./agent-a.md#a4-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Governance config](./agent-b.md#b1-governance-config)
- [Blockchain client](./agent-b.md#b2-blockchain-client)
- [On-chain proposals](./agent-b.md#b3-on-chain-proposals)
- [On-chain voting](./agent-b.md#b4-on-chain-voting)
- [Timelock execution](./agent-b.md#b5-timelock-execution)
- [Tests](./agent-b.md#b6-tests)
- [Governance tx types](./agent-b.md#b7-governance-tx-types)
- [Governance tx payload validation](./agent-b.md#b8-governance-tx-payload-validation)
- [CLI commands](./agent-b.md#b9-cli-commands)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.7.3 Target |
|-----------|----------|---------------|---------------|
| **Governance service** | `apps/governance/src/governance_service/` (991 lines) | ✅ EXISTS — FastAPI app, domain models, service layer, PostgreSQL storage | Wire to blockchain-node for on-chain proposals/votes |
| **Domain models** | `domain/governance.py` (243 lines) | ✅ EXISTS — Proposal, Vote, Delegation, GovernanceToken, TokenStake, DaoTreasury, ProposalExecutionLog, TransparencyReport | Add `chain_id`, `block_height`, `tx_hash` fields to Proposal/Vote |
| **Service layer** | `services/governance_service.py` (236 lines) | ✅ EXISTS — CRUD for profiles, proposals, votes; staking, delegation, execution logging | Add blockchain RPC client, on-chain tx submission, balance snapshot |
| **FastAPI app** | `main.py` (410 lines) | ✅ EXISTS — 20+ endpoints (profiles, proposals, votes, treasury, analytics, execute, stake, delegate) | Add blockchain config, on-chain proposal/vote submission endpoints |
| **Governance config** | — | ❌ NONE — no Settings/BaseSettings, no blockchain_rpc_url, no chain_id | Create Settings class with blockchain_rpc_url (8202), default_chain_id, voting params |
| **Blockchain tx types** | `rpc/transactions.py:21-32` | ⚠️ TransactionRequest has `type: str = "TRANSFER"` — arbitrary string, no enum | Add GOVERNANCE_PROPOSE, GOVERNANCE_VOTE, GOVERNANCE_EXECUTE to tx type handling in poa.py |
| **Tx processing** | `consensus/poa.py:348-366` | ✅ Handles arbitrary `type` from `tx.content` — already stores it | Add governance-specific payload validation for GOVERNANCE_* types |
| **Account balance query** | `rpc/accounts.py:30` — `GET /rpc/account/{address}` | ✅ EXISTS — returns account info including balance | Governance service queries this for vote weight snapshot |
| **Pool Hub** | `apps/pool-hub/` | ✅ EXISTS (v0.6.7 complete) — PoolHubBlockchainClient, Settings, miner registration, rewards | NOT a v0.7.3 target — parameter API deferred to v0.8.x |
| **Pool Hub parameter API** | — | ❌ NONE — no endpoint to change reward rates, scoring weights | DEFERRED to v0.8.x (parameter automation) |
| **Bridge (v0.7.0-v0.7.2)** | `aitbc/bridge/`, `cross_chain/bridge.py` | ✅ v0.7.0+v0.7.1 complete, v0.7.2 Agent A complete, Agent B in progress | NOT used in v0.7.3 (same-chain only) — cross-chain governance deferred |
| **CLI governance commands** | `cli/aitbc_cli/commands/` | ❌ NONE — no governance command group | Add `governance` command group (propose, vote, list, execute, status) |
| **Proposal execution** | `main.py:167-188` — `execute_proposal()` | ⚠️ LOCAL ONLY — updates status to "executed", `tx_hash: None`, no blockchain tx | Submit GOVERNANCE_EXECUTE tx after timelock; record tx_hash |
| **Voting power** | `services/governance_service.py` — local GovernanceToken table | ⚠️ LOCAL — staking-based, not on-chain balance | Add on-chain balance snapshot via blockchain-node RPC |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Governance service exists** — 991 lines, FastAPI app, domain models, service layer
2. ✅ **Domain models complete** — Proposal, Vote, Delegation, GovernanceToken, TokenStake, DaoTreasury, ProposalExecutionLog, TransparencyReport
3. ✅ **20+ API endpoints exist** — profiles, proposals, votes, treasury, analytics, execute, stake, delegate
4. ✅ **PostgreSQL storage with Alembic migrations** — `apps/governance/alembic/`
5. ✅ **Blockchain-node has account balance query** — `GET /rpc/account/{address}` returns balance
6. ✅ **TransactionRequest accepts arbitrary type string** — `type: str = "TRANSFER"` at `rpc/transactions.py:30`
7. ✅ **Tx processing stores type** — `poa.py:348-366` reads `tx.content.get("type", "TRANSFER")` and stores it
8. ✅ **Pool Hub exists** — v0.6.7 complete (commit `5bb3803bd`)
9. ✅ **v0.7.0-v0.7.1 complete** — bridge basics + security (multi-sig, validator sets, block header sigs)

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/governance/` (new package), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 9 items | `apps/governance/`, `apps/blockchain-node/`, `cli/` |

**Conflict boundary**: Agent A owns `aitbc/governance/` (new package). Agent B owns `apps/governance/`, `apps/blockchain-node/`, `cli/`. Agent B consumes Agent A's governance types, client, and on-chain utilities.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3. B7-B8 (blockchain-node tx types) can proceed independently.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.3 — Governance
