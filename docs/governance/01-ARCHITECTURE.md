# AITBC Governance Architecture

## Overview

The AITBC Governance system consists of two live components — the **Governance Service** (port 8105) and the **CLI Commands** — plus a set of **reference Solidity contracts** under `contracts/governance/` that document the EVM design but are **not** the operating path of the live Python chain. There is also a chain-side governance surface on the blockchain node (`/rpc/v1/governance/*`, `X-API-Key` gated; `GOVERNANCE_EXECUTE` senders must be listed in the `governance_executors` chain parameter). These components work together to enable decentralized decision-making through token-weighted voting, staking, and delegation.

## Components

### 1. Governance Service

**Port:** 8105

**Technology Stack:**

- FastAPI (Python web framework)
- SQLModel (ORM)
- SQLite (default) or PostgreSQL (production)
- Alembic (database migrations)

**Responsibilities:**

- API endpoint management
- Database operations
- Token staking logic
- Voting power calculation
- Delegation management
- Proposal execution logging

**Location:** `/opt/aitbc/apps/governance/`

### 2. Smart Contracts — reference design, not the operating path

> **⚠️ Not the live implementation.** The Solidity contracts below are a reference EVM design. The live governance path is the Python governance service on port 8105 (`apps/governance/`) backed by the chain models — voting power is derived **server-side** from the voter's on-chain balance/stake snapshot (a caller-supplied `voting_power` in a vote request is ignored/overwritten). Chain-side, `/rpc/v1/governance/*` routes submit `GOVERNANCE_PROPOSE`/`GOVERNANCE_VOTE`/`GOVERNANCE_EXECUTE` transactions; `GOVERNANCE_EXECUTE` is restricted to addresses in the `governance_executors` chain parameter. None of the mechanics below (30-day locks, 2x multiplier, 10% quorum, 1-day delay) are enforced by the running system.

**Technology Stack:**

- Solidity ^0.8.19
- OpenZeppelin contracts
- Foundry (testing framework)

**Contracts (reference):**

#### AITBCGovernanceToken.sol

- ERC20 token with 1B total supply
- Token staking with minimum 30-day lock period
- 2x voting power multiplier for staked tokens
- Automatic voting power recalculation on transfers

**Location:** `/opt/aitbc/contracts/governance/src/AITBCGovernanceToken.sol`

#### AITBCVoting.sol

- Proposal creation with configurable voting periods
- Token-weighted voting
- Quorum requirements (10% of total supply)
- Execution delay (1 day after voting ends)
- Proposal execution with on-chain enforcement

**Location:** `/opt/aitbc/contracts/governance/src/AITBCVoting.sol`

### 3. CLI Commands

**Technology Stack:**

- Click (Python CLI framework)
- AITBCHTTPClient (HTTP client)

**Command Group:** `aitbc governance`

**Available Commands:**

- `propose` - Create a governance proposal
- `vote` - Cast a vote on a proposal
- `list` - List proposals (optional status/category/proposer filters)
- `execute` - Execute a passed proposal
- `close` - Close a proposal
- `status` - Get governance service status
- `get` - Get a specific proposal by ID
- `propagate` - Propagate a proposal to target chains
- `aggregate-votes` - Aggregate votes for a proposal
- `execute-cross-chain` - Execute a proposal cross-chain

Staking is **not** part of the governance group: use `aitbc stake` / `aitbc unstake` / `aitbc liquidity-stake` or `aitbc wallet stake` (`cli/aitbc_cli/commands/staking.py`, `commands/wallet/staking.py`).

**Location:** `/opt/aitbc/cli/aitbc_cli/commands/governance.py` (talks to the governance service REST API on port 8105)

## Data Flow

### Proposal Creation Flow

1. User creates proposal via CLI (`aitbc governance propose`) or API (`POST /v1/governance/proposals` on 8105)
2. Proposal stored in the governance service database
3. When `enable_onchain_submission` is configured, a `GOVERNANCE_PROPOSE` transaction is submitted to the chain
4. Voting period begins

### Voting Flow

1. User votes via CLI (`aitbc governance vote`) or API (`POST /v1/governance/votes`)
2. Vote recorded in database with `voter_address`
3. The server derives voting power from the voter's **on-chain balance/stake snapshot** — caller-supplied `voting_power` is ignored
4. When on-chain submission is enabled, a `GOVERNANCE_VOTE` transaction is submitted and the tx hash recorded on the vote

### Proposal Execution Flow

1. Voting period ends
2. Quorum and approval thresholds checked
3. `aitbc governance execute` / `POST /v1/governance/execute` triggers execution
4. On-chain, the resulting `GOVERNANCE_EXECUTE` transaction is only accepted from addresses listed in the `governance_executors` chain parameter
5. Execution logged in database

### Staking Flow

1. User stakes via `aitbc stake` / `aitbc wallet stake` (POST `/rpc/staking/stake` on the blockchain node)
2. Stake is recorded on-chain as an active stake for the address
3. Voting power derives from the resulting on-chain balance/stake — there is no separate "2x multiplier" contract in the live path
4. `POST /v1/governance/stake` on the governance service also records the stake and refreshes cached voting power

### Delegation Flow

1. User delegates voting power via API (`POST /v1/governance/delegate` on 8105)
2. Delegation recorded in database
3. Voting power transferred to delegate

## System Diagram

```
┌─────────────────┐
│   CLI Commands  │
│  (aitbc gov)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Governance API  │
│   (Port 8105)   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌─────────┐ ┌─────────────┐
│ Database│ │ Blockchain  │
│ (SQLite │ │ node        │
│ /PostgreSQL)│ GOVERNANCE_* txs│
└─────────┘ └─────────────┘
```

## Integration Points

### API Gateway

- Route: `/v1/governance/*`
- Forwards requests to Governance Service (port 8105)

### Blockchain Node

- `/rpc/v1/governance/*` routes (`X-API-Key` gated) for chain-side proposal/vote/execute transactions
- On-chain `GOVERNANCE_PROPOSE` / `GOVERNANCE_VOTE` / `GOVERNANCE_EXECUTE` transaction types; `GOVERNANCE_EXECUTE` senders must appear in the `governance_executors` chain parameter
- Source of the on-chain balance/stake snapshot used for voting power

### Database

- SQLite for development
- PostgreSQL for production
- Alembic for schema migrations

## Security Architecture

### Authentication

- Wallet-based authentication for CLI commands
- service-to-service calls go through the api-gateway; the governance service itself has no API-key middleware (X-API-Key gating lives on blockchain-node `/rpc/*`)

### Authorization

- Token holders can vote
- Voting power is derived server-side from on-chain balance + active stake (caller-supplied `voting_power` is ignored)
- `GOVERNANCE_EXECUTE` on-chain is restricted to `governance_executors` addresses
- Delegation allows proxy voting

### Audit Trail

- All proposal executions logged
- Vote records with timestamps
- Staking and delegation history

## Scalability Considerations

### Database — Scalability Considerations

- Connection pooling for PostgreSQL
- Indexed queries for performance
- Migration support for schema changes

### Smart Contracts (reference design)

- Gas optimization for voting operations
- Batch operations for efficiency
- Event logging for off-chain indexing
- Not deployed/executed by the live Python chain — see the note in [Components](#2-smart-contracts--reference-design-not-the-operating-path)

### API

- Async I/O for concurrent requests
- Caching for frequently accessed data
- Rate limiting for abuse prevention
