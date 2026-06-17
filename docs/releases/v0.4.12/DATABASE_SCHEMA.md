# Database Schema - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces a comprehensive database schema for the governance service, including tables for proposals, votes, delegations, governance tokens, token stakes, and proposal execution logs. The schema includes 14 database indexes for performance optimization.

## Tables

### Proposals Table

Stores governance proposals with voting status and execution state.

```sql
CREATE TABLE proposals (
    proposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposer_address VARCHAR(42) NOT NULL,
    proposal_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    proposal_value JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    voting_start TIMESTAMP WITH TIME ZONE,
    voting_end TIMESTAMP WITH TIME ZONE,
    quorum_required BIGINT NOT NULL DEFAULT 1000000,
    yes_votes BIGINT NOT NULL DEFAULT 0,
    no_votes BIGINT NOT NULL DEFAULT 0,
    execution_tx_hash VARCHAR(66),
    execution_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_proposals_status ON proposals(status);
CREATE INDEX idx_proposals_voting_period ON proposals(voting_start, voting_end);
CREATE INDEX idx_proposals_proposer ON proposals(proposer_address);
```

### Votes Table

Stores individual votes with voting power and delegation information.

```sql
CREATE TABLE votes (
    vote_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id UUID NOT NULL REFERENCES proposals(proposal_id) ON DELETE CASCADE,
    voter_address VARCHAR(42) NOT NULL,
    vote BOOLEAN NOT NULL,
    voting_power BIGINT NOT NULL,
    vote_weight BIGINT NOT NULL,
    delegated_from VARCHAR(42),
    voted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    signature VARCHAR(130),
    UNIQUE(proposal_id, voter_address)
);

CREATE INDEX idx_votes_proposal ON votes(proposal_id);
CREATE INDEX idx_votes_voter ON votes(voter_address);
CREATE INDEX idx_votes_delegated ON votes(delegated_from);
```

### Delegations Table

Stores voting power delegations between addresses.

```sql
CREATE TABLE delegations (
    delegation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delegator_address VARCHAR(42) NOT NULL,
    delegate_address VARCHAR(42) NOT NULL,
    voting_power BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(delegator_address, delegate_address, is_active)
);

CREATE INDEX idx_delegations_delegator ON delegations(delegator_address);
CREATE INDEX idx_delegations_delegate ON delegations(delegate_address);
CREATE INDEX idx_delegations_active ON delegations(is_active, expires_at);
```

### Governance Tokens Table

Stores token holdings, staking information, and voting power.

```sql
CREATE TABLE governance_tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    holder_address VARCHAR(42) NOT NULL,
    token_balance BIGINT NOT NULL DEFAULT 0,
    staked_tokens BIGINT NOT NULL DEFAULT 0,
    voting_power BIGINT NOT NULL DEFAULT 0,
    rewards_claimed BIGINT NOT NULL DEFAULT 0,
    rewards_pending BIGINT NOT NULL DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(holder_address)
);

CREATE INDEX idx_tokens_holder ON governance_tokens(holder_address);
CREATE INDEX idx_tokens_voting_power ON governance_tokens(voting_power DESC);
```

### Token Staking Table

Stores token staking records with lock periods and rewards.

```sql
CREATE TABLE token_stakes (
    stake_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staker_address VARCHAR(42) NOT NULL,
    amount_staked BIGINT NOT NULL,
    lock_period_days INTEGER NOT NULL,
    staked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    unstakes_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    rewards_earned BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_stakes_staker ON token_stakes(staker_address);
CREATE INDEX idx_stakes_active ON token_stakes(is_active, unstakes_at);
```

### Proposal Execution Log Table

Stores execution logs for proposal tracking and auditing.

```sql
CREATE TABLE proposal_execution_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id UUID NOT NULL REFERENCES proposals(proposal_id),
    execution_step VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    result JSONB,
    error_message TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_execution_log_proposal ON proposal_execution_log(proposal_id);
```

## Migration

### Database Migration

```bash
# Run database migrations
alembic upgrade head

# Verify schema creation
psql -d aitbc_governance -c "\dt"
```

### Verification

```bash
# Verify database schema
psql -d aitbc_governance -c "\d proposals"
psql -d aitbc_governance -c "\d votes"
psql -d aitbc_governance -c "\d delegations"

# Check data consistency
psql -d aitbc_governance -c "SELECT COUNT(*) FROM proposals;"
```

## Performance Optimization

- **14 database indexes** for common query patterns
- **Cascade deletes** for referential integrity
- **JSONB columns** for flexible metadata storage
- **Timestamp with time zone** for accurate time tracking

---

*Last Updated: 2026-06-07*
