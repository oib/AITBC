# Database Schema

## Overview

The Governance Service uses SQLModel with SQLite (default) or PostgreSQL (production). The schema includes 9 tables and 14 indexes for performance optimization.

## Tables

### governance_profiles

User governance profiles for managing user roles and permissions.

| Column | Type | Description |
|--------|------|-------------|
| profile_id | UUID | Primary key |
| user_id | VARCHAR | User identifier |
| role | VARCHAR | User role (admin, voter, etc.) |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

### proposals

Governance proposals with v0.4.12 enhancements including execution tracking.

| Column | Type | Description |
|--------|------|-------------|
| proposal_id | UUID | Primary key |
| proposer_id | VARCHAR | Proposer identifier |
| title | VARCHAR | Proposal title |
| description | TEXT | Proposal description |
| category | VARCHAR | Proposal category |
| status | VARCHAR | Status (draft, active, succeeded, rejected, executed) |
| voting_starts | TIMESTAMP | Voting start time |
| voting_ends | TIMESTAMP | Voting end time |
| executed_at | TIMESTAMP | Execution timestamp |
| proposal_metadata | JSONB | Additional metadata |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

### votes

Vote records with token-weighted power tracking.

| Column | Type | Description |
|--------|------|-------------|
| vote_id | UUID | Primary key |
| proposal_id | UUID | Foreign key to proposals |
| voter_id | VARCHAR | Voter identifier |
| vote_type | VARCHAR | Vote type (for, against, abstain) |
| voting_power | INTEGER | Voting power used |
| reason | TEXT | Vote reason |
| created_at | TIMESTAMP | Creation timestamp |

### delegations

Voting power delegations for proxy voting.

| Column | Type | Description |
|--------|------|-------------|
| delegation_id | UUID | Primary key |
| delegator_address | VARCHAR | Delegator address |
| delegate_address | VARCHAR | Delegate address |
| voting_power | INTEGER | Delegated voting power |
| is_active | BOOLEAN | Active status |
| created_at | TIMESTAMP | Creation timestamp |

### governance_tokens

Token holdings and voting power tracking.

| Column | Type | Description |
|--------|------|-------------|
| token_id | UUID | Primary key |
| holder_address | VARCHAR | Token holder address |
| token_balance | DECIMAL | Token balance |
| staked_tokens | DECIMAL | Staked token amount |
| voting_power | DECIMAL | Total voting power |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

### token_stakes

Token staking records with lock periods.

| Column | Type | Description |
|--------|------|-------------|
| stake_id | UUID | Primary key |
| staker_address | VARCHAR | Staker address |
| amount_staked | DECIMAL | Amount staked |
| lock_period_days | INTEGER | Lock period in days |
| unstakes_at | TIMESTAMP | Unstake timestamp |
| is_active | BOOLEAN | Active status |
| created_at | TIMESTAMP | Creation timestamp |

### proposal_execution_log

Proposal execution audit trail.

| Column | Type | Description |
|--------|------|-------------|
| log_id | UUID | Primary key |
| proposal_id | UUID | Foreign key to proposals |
| execution_step | VARCHAR | Execution step name |
| status | VARCHAR | Status (pending, completed, failed) |
| result | JSONB | Execution result |
| error_message | TEXT | Error message if failed |
| created_at | TIMESTAMP | Creation timestamp |

### dao_treasury

DAO treasury records for financial tracking.

| Column | Type | Description |
|--------|------|-------------|
| treasury_id | VARCHAR | Primary key |
| balance | DECIMAL | Treasury balance |
| last_updated | TIMESTAMP | Last update timestamp |

### transparency_reports

Governance analytics reports.

| Column | Type | Description |
|--------|------|-------------|
| report_id | UUID | Primary key |
| report_type | VARCHAR | Report type |
| period | VARCHAR | Reporting period |
| data | JSONB | Report data |
| created_at | TIMESTAMP | Creation timestamp |

## Indexes

14 indexes for performance optimization:

### Proposal Indexes
- `idx_proposals_status` - Status filtering
- `idx_proposals_voting_period` - Voting period queries
- `idx_proposals_proposer` - Proposer queries

### Vote Indexes
- `idx_votes_proposal` - Proposal vote queries
- `idx_votes_voter` - Voter history queries

### Delegation Indexes
- `idx_delegations_delegator` - Delegator queries
- `idx_delegations_delegate` - Delegate queries

### Token Indexes
- `idx_tokens_holder` - Holder queries
- `idx_tokens_voting_power` - Voting power queries

### Stake Indexes
- `idx_stakes_staker` - Staker queries
- `idx_stakes_unstakes_at` - Unstake scheduling

### Execution Log Indexes
- `idx_execution_log_proposal` - Proposal execution history
- `idx_execution_log_status` - Status filtering

## Database Types

### SQLite (Default)
- **Location:** `/var/lib/aitbc/data/governance_service.db`
- **Use Case:** Development and testing
- **Advantages:** No setup required, portable
- **Limitations:** Single-writer, limited concurrency

### PostgreSQL (Production)
- **Database:** `aitbc_governance`
- **User:** `aitbc_governance`
- **Use Case:** Production deployment
- **Advantages:** Multi-writer, better concurrency, advanced features
- **Setup:** See [Configuration](08-CONFIGURATION.md)

## Relationships

```
proposals (1) ────────< (N) votes
proposals (1) ────────< (N) proposal_execution_log
governance_tokens (1) ──< (N) token_stakes
governance_tokens (1) ──< (N) delegations (as delegator)
governance_tokens (1) ──< (N) delegations (as delegate)
```

## Migration History

### Migration 001: Initial Governance Schema
- Created all 9 tables
- Added 14 indexes
- Set up foreign key relationships
- Applied: June 7, 2026

See [Migrations](06-MIGRATIONS.md) for migration procedures.
