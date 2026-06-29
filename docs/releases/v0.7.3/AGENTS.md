# v0.7.3 — Agent Task Assignment

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

### Architecture: Governance (v0.7.3)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/governance/ — NEW PACKAGE)                        │
│                                                                      │
│  Governance types (A1 — NEW types.py):                               │
│    GovernanceTxType enum — PROPOSE, VOTE, EXECUTE                    │
│    GovernanceConfig — voting params, timelock, quorum                │
│    ProposalData, VoteData — on-chain tx payload dataclasses          │
│    ParameterChangeSchema — what params, which service, old→new       │
│                                                                      │
│  Governance client (A2 — NEW client.py):                             │
│    GovernanceClient — async HTTP client for governance service RPC   │
│    submit_proposal, submit_vote, execute_proposal, get_status        │
│                                                                      │
│  On-chain utilities (A3 — NEW onchain.py):                           │
│    build_proposal_tx(proposal_data) — GOVERNANCE_PROPOSE tx payload  │
│    build_vote_tx(vote_data) — GOVERNANCE_VOTE tx payload             │
│    build_execute_tx(proposal_id) — GOVERNANCE_EXECUTE tx payload     │
│    validate_governance_payload(tx_type, payload) — field validation  │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Governance Service                   │
│                         │    │ (apps/governance/)                   │
│  governance propose     │    │                                      │
│  governance vote        │    │  Config (B1):                        │
│  governance list        │    │    Settings class (blockchain_rpc_url,│
│  governance execute     │    │    chain_id, voting params)           │
│  governance status      │    │                                      │
│                         │    │  Blockchain client (B2):             │
│  Uses GovernanceClient  │    │    AITBCHTTPClient → query balance    │
│  (A2) + shared types    │    │    Submit GOVERNANCE_* txs            │
│                         │    │                                      │
│                         │    │  On-chain proposals (B3):            │
│                         │    │    Proposal → GOVERNANCE_PROPOSE tx   │
│                         │    │    Store tx_hash, block_height        │
│                         │    │                                      │
│                         │    │  On-chain voting (B4):               │
│                         │    │    Vote → GOVERNANCE_VOTE tx          │
│                         │    │    Vote weight = on-chain balance    │
│                         │    │    at snapshot block                  │
│                         │    │                                      │
│                         │    │  Timelock execution (B5):            │
│                         │    │    Execute → GOVERNANCE_EXECUTE tx    │
│                         │    │    After timelock expires             │
│                         │    │    Record tx_hash                     │
│                         │    │                                      │
│                         │    │  Tests (B6):                         │
│                         │    │    Proposal → vote → execute flow     │
└─────────────────────────┘    └──────────────────────────────────────┘

  Blockchain Node (apps/blockchain-node/) — Agent B:
    B7: Add GOVERNANCE_* tx type validation in poa.py
    B8: Add governance tx payload validation (uses A3)
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/governance/` (new package), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/governance/src/`, `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`, `cli/aitbc_cli/commands/governance.py` (new), `apps/governance/tests/` |

**Conflict boundary**: Agent A owns `aitbc/governance/` package (new). Agent B owns `apps/governance/`, `apps/blockchain-node/`, and `cli/`. Agent B consumes Agent A's `GovernanceClient`, governance types, and on-chain utilities. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3 (B2-B5 depend on A1 types + A3 utilities). B1 (config) can proceed in parallel with Agent A.

---

## Agent A — Shared Core

**Scope**: Create a new `aitbc/governance/` package with governance transaction types, on-chain payload builders, and a GovernanceClient for the governance service RPC. These are dependency-free shared types consumed by the governance service and CLI.

**Working directory**: `/opt/aitbc/aitbc/governance/`

**Prerequisite**: v0.7.1 ✅, v0.7.2 Agent A ✅. v0.7.2 Agent B is in progress but v0.7.3 is same-chain only — no bridge dependency.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/governance/ && ./venv/bin/python -m ruff check aitbc/governance/ tests/unit/test_governance_sdk.py && ./venv/bin/python -m pytest tests/unit/test_governance_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/governance/types.py` — GovernanceTxType enum, GovernanceConfig, ProposalData, VoteData, ParameterChangeSchema | 🔴 P0 | `aitbc/governance/types.py` (new), `aitbc/governance/__init__.py` (new) | ⬜ |
| A2 | Create `aitbc/governance/client.py` — GovernanceClient async HTTP client for governance service RPC | 🔴 P0 | `aitbc/governance/client.py` (new), `aitbc/governance/__init__.py` (extend) | ⬜ |
| A3 | Create `aitbc/governance/onchain.py` — on-chain tx payload builders + validation | 🔴 P0 | `aitbc/governance/onchain.py` (new), `aitbc/governance/__init__.py` (extend) | ⬜ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_governance_sdk.py` (new) | ⬜ |

### Agent A — Detailed Instructions

#### A1: Governance Types

Create `aitbc/governance/types.py`:

```python
class GovernanceTxType(StrEnum):
    """Governance transaction types for on-chain proposals/votes/execution."""
    PROPOSE = "GOVERNANCE_PROPOSE"
    VOTE = "GOVERNANCE_VOTE"
    EXECUTE = "GOVERNANCE_EXECUTE"


@dataclass
class GovernanceConfig:
    """Configuration for governance operations."""
    rpc_url: str = "http://localhost:8107"  # governance service port
    blockchain_rpc_url: str = "http://localhost:8202"
    chain_id: str = "ait-hub"
    voting_period_blocks: int = 7200  # ~2 days at 2s block time
    quorum_percent: float = 30.0
    approval_percent: float = 50.0
    timelock_blocks: int = 86400  # 48h at 2s block time
    snapshot_delay_blocks: int = 100  # blocks before voting starts


@dataclass
class ProposalData:
    """Payload for a GOVERNANCE_PROPOSE transaction."""
    proposal_id: str
    proposer: str
    title: str
    description: str
    proposal_type: str  # parameter_change, fund_allocation, validator_change, emergency
    parameters: dict[str, Any] = field(default_factory=dict)
    voting_starts_block: int = 0
    voting_ends_block: int = 0


@dataclass
class VoteData:
    """Payload for a GOVERNANCE_VOTE transaction."""
    proposal_id: str
    voter: str
    vote_type: str  # "for", "against", "abstain"
    voting_power: float = 0.0  # snapshot balance
    reason: str = ""


@dataclass
class ParameterChangeSchema:
    """Schema for a parameter change proposal."""
    target_service: str  # "blockchain", "pool-hub", "marketplace"
    parameter_name: str
    old_value: Any
    new_value: Any
    description: str = ""
```

#### A2: Governance Client

Create `aitbc/governance/client.py` — async HTTP client for the governance service, following the same pattern as `aitbc/bridge/client.py`:

```python
class GovernanceClient:
    """HTTP client for the governance service RPC endpoints."""
    # Wraps: POST /v1/governance/proposals, POST /v1/governance/votes,
    # POST /v1/governance/execute, GET /v1/governance/proposals/{id},
    # GET /v1/governance/status
```

Methods: `create_proposal`, `cast_vote`, `execute_proposal`, `get_proposal`, `list_proposals`, `get_status`, `get_voting_power`.

#### A3: On-Chain Utilities

Create `aitbc/governance/onchain.py`:

```python
def build_proposal_tx(data: ProposalData) -> dict[str, Any]:
    """Build a GOVERNANCE_PROPOSE transaction payload."""

def build_vote_tx(data: VoteData) -> dict[str, Any]:
    """Build a GOVERNANCE_VOTE transaction payload."""

def build_execute_tx(proposal_id: str, executor: str) -> dict[str, Any]:
    """Build a GOVERNANCE_EXECUTE transaction payload."""

def validate_governance_payload(tx_type: GovernanceTxType, payload: dict[str, Any]) -> list[str]:
    """Validate a governance transaction payload. Returns list of errors."""
```

#### A4: Unit Tests

`tests/unit/test_governance_sdk.py` — tests for all types, client (mocked httpx), and on-chain utilities.

---

## Agent B — Apps & Infrastructure

**Scope**: Add governance service config, blockchain RPC client, on-chain proposal/vote/execution submission, balance snapshot for voting power, timelock execution, governance tx type validation in blockchain-node, CLI commands, integration tests.

**Working directory**: `/opt/aitbc/apps/governance/`, `/opt/aitbc/apps/blockchain-node/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A3 complete. v0.7.2 Agent B complete (for consensus path stability).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/governance/src/ apps/blockchain-node/src/aitbc_chain/consensus/poa.py cli/aitbc_cli/commands/governance.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/governance/tests/test_v073_governance.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add governance service Settings class (blockchain_rpc_url, chain_id, voting params) | 🔴 P0 | `apps/governance/src/governance_service/config.py` (new) | ⬜ |
| B2 | Add blockchain RPC client to governance service (query balance, submit txs) | 🔴 P0 | `apps/governance/src/governance_service/clients/blockchain.py` (new) | ⬜ |
| B3 | On-chain proposal submission — GOVERNANCE_PROPOSE tx | 🔴 P0 | `apps/governance/src/governance_service/services/governance_service.py`, `main.py` | ⬜ |
| B4 | On-chain voting with balance snapshot — GOVERNANCE_VOTE tx | 🔴 P0 | `apps/governance/src/governance_service/services/governance_service.py`, `main.py` | ⬜ |
| B5 | Timelock execution — GOVERNANCE_EXECUTE tx after timelock | 🔴 P0 | `apps/governance/src/governance_service/services/governance_service.py`, `main.py` | ⬜ |
| B6 | Add domain model fields — chain_id, block_height, tx_hash on Proposal/Vote | High | `apps/governance/src/governance_service/domain/governance.py` | ⬜ |
| B7 | Add GOVERNANCE_* tx type validation in blockchain-node poa.py | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ⬜ |
| B8 | CLI governance commands + integration tests | High | `cli/aitbc_cli/commands/governance.py` (new), `apps/governance/tests/test_v073_governance.py` (new) | ⬜ |

### Agent B — Detailed Instructions

#### B1: Governance Service Config

Create `apps/governance/src/governance_service/config.py`:
```python
class Settings(BaseSettings):
    blockchain_rpc_url: str = "http://localhost:8202"  # NOT 8006
    default_chain_id: str = "ait-hub"
    voting_period_blocks: int = 7200
    quorum_percent: float = 30.0
    approval_percent: float = 50.0
    timelock_blocks: int = 86400
    snapshot_delay_blocks: int = 100
```

#### B2: Blockchain RPC Client

Create `apps/governance/src/governance_service/clients/blockchain.py` — wraps `AITBCHTTPClient` (or `httpx.AsyncClient`) for:
- `get_balance(address, chain_id)` → `GET /rpc/account/{address}`
- `submit_transaction(tx_data)` → `POST /rpc/transactions`
- `get_block_height(chain_id)` → `GET /rpc/chain/{chain_id}/height`

#### B3-B5: On-Chain Proposals, Voting, Execution

Wire the governance service to submit GOVERNANCE_* transactions:
- **B3**: `create_proposal()` → build GOVERNANCE_PROPOSE tx (using A3 `build_proposal_tx`) → submit to blockchain-node → store tx_hash + block_height
- **B4**: `cast_vote()` → query voter's on-chain balance at snapshot block → build GOVERNANCE_VOTE tx → submit → store tx_hash
- **B5**: `execute_proposal()` → check timelock expired → build GOVERNANCE_EXECUTE tx → submit → store tx_hash

#### B6: Domain Model Fields

Add to `Proposal`: `chain_id: str = "ait-hub"`, `block_height: int | None = None`, `tx_hash: str | None = None`
Add to `Vote`: `chain_id: str = "ait-hub"`, `block_height: int | None = None`, `tx_hash: str | None = None`
Add Alembic migration.

#### B7: Blockchain-Node Tx Type Validation

In `consensus/poa.py` (line 348 area), add validation for GOVERNANCE_* tx types:
- Check that GOVERNANCE_PROPOSE payloads have required fields (proposal_id, title, proposer)
- Check that GOVERNANCE_VOTE payloads have required fields (proposal_id, voter, vote_type)
- Check that GOVERNANCE_EXECUTE payloads have required fields (proposal_id, executor)
- Use `aitbc.governance.onchain.validate_governance_payload()` from A3

#### B8: CLI + Integration Tests

CLI: `cli/aitbc_cli/commands/governance.py` — command group:
- `aitbc governance propose --title "..." --type parameter_change --params ...`
- `aitbc governance vote --proposal-id prop_xxx --vote for`
- `aitbc governance list [--status active]`
- `aitbc governance execute --proposal-id prop_xxx`
- `aitbc governance status`

Tests: `apps/governance/tests/test_v073_governance.py` — proposal → vote → execute flow on single chain.

---

## Coordination

### Shared Files

No shared files are touched by both agents. Agent A owns `aitbc/governance/` (new package). Agent B owns `apps/governance/`, `apps/blockchain-node/`, and `cli/`.

### Sequencing

1. **Phase 1** (parallel): Agent A starts A1-A3 (shared SDK), Agent B starts B1 (config) + B6 (domain fields)
2. **Phase 2** (Agent A first): Agent A completes A4 (tests), Agent B starts B2-B5 (blockchain client, on-chain submission — depends on A1 types + A3 utilities)
3. **Phase 3** (Agent B): B7 (blockchain-node tx validation — depends on A3), B8 (CLI + tests)

### Dependencies

```
v0.7.2 Agent B (consensus path stability)
    │
    ├── A1 (types) ──┐
    ├── A2 (client) ─┤
    ├── A3 (onchain) ─┤
    │                  ├── A4 (tests)
    │                  │
    ├── B1 (config) ──┐│
    ├── B6 (fields) ──┤│
    │                  │├── B2 (blockchain client)
    │                  │├── B3 (on-chain proposals)
    │                  │├── B4 (on-chain voting)
    │                  │├── B5 (timelock execution)
    │                  │├── B7 (tx validation — needs A3)
    │                  │└── B8 (CLI + tests)
```

### Deferred to v0.8.x

- **Cross-chain governance**: Proposal propagation via bridge, cross-chain vote aggregation — requires v0.7.2 verification operational + tested
- **Parameter automation**: Pool-hub/marketplace parameter change APIs — requires target services to expose parameter endpoints
- **Emergency proposals**: Shorter timelock, higher quorum — can be added in v0.7.3 if time permits, otherwise v0.8.x
