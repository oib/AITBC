# AITBC Governance Architecture

## Overview

The AITBC Governance system consists of three main components: the Governance Service, Smart Contracts, and CLI Commands. These components work together to enable decentralized decision-making through token-weighted voting, staking, and delegation.

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

### 2. Smart Contracts

**Technology Stack:**
- Solidity ^0.8.19
- OpenZeppelin contracts
- Foundry (testing framework)

**Contracts:**

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
- `stake` - Stake tokens for enhanced voting power
- `delegate` - Delegate voting power to another address
- `execute` - Execute a passed proposal
- `voting-power` - Get voting power for an address
- `vote` - Vote on a governance proposal
- `proposal` - Create a governance proposal

**Location:** `/opt/aitbc/cli/aitbc_cli/commands/operations.py`

## Data Flow

### Proposal Creation Flow
1. User creates proposal via CLI or API
2. Proposal stored in database
3. Smart contract proposal created on-chain
4. Voting period begins

### Voting Flow
1. User votes via CLI or API
2. Vote recorded in database
3. Smart contract vote submitted on-chain
4. Voting power calculated from token holdings + staking

### Proposal Execution Flow
1. Voting period ends
2. Quorum and approval thresholds checked
3. Execution delay passes (1 day)
4. Proposal executed on-chain
5. Execution logged in database

### Staking Flow
1. User stakes tokens via CLI or API
2. Tokens locked in smart contract
3. Voting power updated (2x multiplier)
4. Staking record created in database

### Delegation Flow
1. User delegates voting power via CLI or API
2. Delegation recorded in database
3. Voting power transferred to delegate
4. Smart contract delegation created on-chain

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
│ Database│ │ Smart       │
│ (SQLite │ │ Contracts   │
│ /PostgreSQL)│ (Blockchain)│
└─────────┘ └─────────────┘
```

## Integration Points

### API Gateway
- Route: `/governance/*`
- Forwards requests to Governance Service (port 8105)

### Blockchain Node
- RPC endpoint for smart contract interactions
- On-chain proposal and vote submission

### Database
- SQLite for development
- PostgreSQL for production
- Alembic for schema migrations

## Security Architecture

### Authentication
- Wallet-based authentication for CLI commands
- API key authentication for service-to-service communication

### Authorization
- Token holders can vote
- Staked tokens get 2x voting power
- Delegation allows proxy voting

### Audit Trail
- All proposal executions logged
- Vote records with timestamps
- Staking and delegation history

## Scalability Considerations

### Database
- Connection pooling for PostgreSQL
- Indexed queries for performance
- Migration support for schema changes

### Smart Contracts
- Gas optimization for voting operations
- Batch operations for efficiency
- Event logging for off-chain indexing

### API
- Async I/O for concurrent requests
- Caching for frequently accessed data
- Rate limiting for abuse prevention
