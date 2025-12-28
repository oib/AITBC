# Governance Module

The AITBC governance module enables decentralized decision-making through proposal voting and parameter changes.

## Overview

The governance system allows AITBC token holders to:
- Create proposals for protocol changes
- Vote on active proposals
- Execute approved proposals
- Track governance history

## API Endpoints

### Get Governance Parameters

Retrieve current governance system parameters.

```http
GET /api/v1/governance/parameters
```

**Response:**
```json
{
  "min_proposal_voting_power": 1000,
  "max_proposal_title_length": 200,
  "max_proposal_description_length": 5000,
  "default_voting_period_days": 7,
  "max_voting_period_days": 30,
  "min_quorum_threshold": 0.01,
  "max_quorum_threshold": 1.0,
  "min_approval_threshold": 0.01,
  "max_approval_threshold": 1.0,
  "execution_delay_hours": 24
}
```

### List Proposals

Get a list of governance proposals.

```http
GET /api/v1/governance/proposals?status={status}&limit={limit}&offset={offset}
```

**Query Parameters:**
- `status` (optional): Filter by proposal status (`active`, `passed`, `rejected`, `executed`)
- `limit` (optional): Number of proposals to return (default: 20)
- `offset` (optional): Number of proposals to skip (default: 0)

**Response:**
```json
[
  {
    "id": "proposal-uuid",
    "title": "Proposal Title",
    "description": "Description of the proposal",
    "type": "parameter_change",
    "target": {},
    "proposer": "user-address",
    "status": "active",
    "created_at": "2025-12-28T18:00:00Z",
    "voting_deadline": "2025-12-28T18:00:00Z",
    "quorum_threshold": 0.1,
    "approval_threshold": 0.5,
    "current_quorum": 0.15,
    "current_approval": 0.75,
    "votes_for": 150,
    "votes_against": 50,
    "votes_abstain": 10,
    "total_voting_power": 1000000
  }
]
```

### Create Proposal

Create a new governance proposal.

```http
POST /api/v1/governance/proposals
```

**Request Body:**
```json
{
  "title": "Reduce Transaction Fees",
  "description": "This proposal suggests reducing transaction fees...",
  "type": "parameter_change",
  "target": {
    "fee_percentage": "0.05"
  },
  "voting_period": 7,
  "quorum_threshold": 0.1,
  "approval_threshold": 0.5
}
```

**Fields:**
- `title`: Proposal title (10-200 characters)
- `description`: Detailed description (50-5000 characters)
- `type`: Proposal type (`parameter_change`, `protocol_upgrade`, `fund_allocation`, `policy_change`)
- `target`: Target configuration for the proposal
- `voting_period`: Voting period in days (1-30)
- `quorum_threshold`: Minimum participation percentage (0.01-1.0)
- `approval_threshold`: Minimum approval percentage (0.01-1.0)

### Get Proposal

Get details of a specific proposal.

```http
GET /api/v1/governance/proposals/{proposal_id}
```

### Submit Vote

Submit a vote on a proposal.

```http
POST /api/v1/governance/vote
```

**Request Body:**
```json
{
  "proposal_id": "proposal-uuid",
  "vote": "for",
  "reason": "I support this change because..."
}
```

**Fields:**
- `proposal_id`: ID of the proposal to vote on
- `vote`: Vote option (`for`, `against`, `abstain`)
- `reason` (optional): Reason for the vote (max 500 characters)

### Get Voting Power

Check a user's voting power.

```http
GET /api/v1/governance/voting-power/{user_id}
```

**Response:**
```json
{
  "user_id": "user-address",
  "voting_power": 10000
}
```

### Execute Proposal

Execute an approved proposal.

```http
POST /api/v1/governance/execute/{proposal_id}
```

**Note:** Proposals can only be executed after:
1. Voting period has ended
2. Quorum threshold is met
3. Approval threshold is met
4. 24-hour execution delay has passed

## Proposal Types

### Parameter Change
Modify system parameters like fees, limits, or thresholds.

**Example Target:**
```json
{
  "transaction_fee": "0.05",
  "min_stake_amount": "1000",
  "max_block_size": "2000"
}
```

### Protocol Upgrade
Initiate a protocol upgrade with version changes.

**Example Target:**
```json
{
  "version": "1.2.0",
  "upgrade_type": "hard_fork",
  "activation_block": 1000000,
  "changes": {
    "new_features": ["feature1", "feature2"],
    "breaking_changes": ["change1"]
  }
}
```

### Fund Allocation
Allocate funds from the treasury.

**Example Target:**
```json
{
  "amount": "1000000",
  "recipient": "0x123...",
  "purpose": "Ecosystem development fund",
  "milestones": [
    {
      "description": "Phase 1 development",
      "amount": "500000",
      "deadline": "2025-06-30"
    }
  ]
}
```

### Policy Change
Update governance or operational policies.

**Example Target:**
```json
{
  "policy_name": "voting_period",
  "new_value": "14 days",
  "rationale": "Longer voting period for better participation"
}
```

## Voting Process

1. **Proposal Creation**: Any user with sufficient voting power can create a proposal
2. **Voting Period**: Token holders vote during the specified voting period
3. **Quorum Check**: Minimum participation must be met
4. **Approval Check**: Minimum approval ratio must be met
5. **Execution Delay**: 24-hour delay before execution
6. **Execution**: Approved changes are implemented

## Database Schema

### GovernanceProposal
- `id`: Unique proposal identifier
- `title`: Proposal title
- `description`: Detailed description
- `type`: Proposal type
- `target`: Target configuration (JSON)
- `proposer`: Address of the proposer
- `status`: Current status
- `created_at`: Creation timestamp
- `voting_deadline`: End of voting period
- `quorum_threshold`: Minimum participation required
- `approval_threshold`: Minimum approval required
- `executed_at`: Execution timestamp
- `rejection_reason`: Reason for rejection

### ProposalVote
- `id`: Unique vote identifier
- `proposal_id`: Reference to proposal
- `voter_id`: Address of the voter
- `vote`: Vote choice (for/against/abstain)
- `voting_power`: Power at time of vote
- `reason`: Vote reason
- `voted_at`: Vote timestamp

### TreasuryTransaction
- `id`: Unique transaction identifier
- `proposal_id`: Reference to proposal
- `from_address`: Source address
- `to_address`: Destination address
- `amount`: Transfer amount
- `status`: Transaction status
- `transaction_hash`: Blockchain hash

## Security Considerations

1. **Voting Power**: Based on AITBC token holdings
2. **Double Voting**: Prevented by tracking voter addresses
3. **Execution Delay**: Prevents rush decisions
4. **Quorum Requirements**: Ensures sufficient participation
5. **Proposal Thresholds**: Prevents spam proposals

## Integration Guide

### Frontend Integration

```javascript
// Fetch proposals
const response = await fetch('/api/v1/governance/proposals');
const proposals = await response.json();

// Submit vote
await fetch('/api/v1/governance/vote', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    proposal_id: 'uuid',
    vote: 'for',
    reason: 'Support this proposal'
  })
});
```

### Smart Contract Integration

The governance system can be integrated with smart contracts for:
- On-chain voting
- Automatic execution
- Treasury management
- Parameter enforcement

## Best Practices

1. **Clear Proposals**: Provide detailed descriptions and rationales
2. **Reasonable Thresholds**: Set achievable quorum and approval thresholds
3. **Community Discussion**: Use forums for proposal discussion
4. **Gradual Changes**: Implement major changes in phases
5. **Monitoring**: Track proposal outcomes and system impact

## Future Enhancements

1. **Delegated Voting**: Allow users to delegate voting power
2. **Quadratic Voting**: Implement more sophisticated voting mechanisms
3. **Time-locked Voting**: Lock tokens for voting power boosts
4. **Multi-sig Execution**: Require multiple signatures for execution
5. **Proposal Templates**: Standardize proposal formats

## Support

For governance-related questions:
- Check the API documentation
- Review proposal history
- Contact the governance team
- Participate in community discussions
