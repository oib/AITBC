# DAO Proposal System - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces a comprehensive DAO proposal system for governance, including proposal types, creation, lifecycle management, and execution.

## Proposal Types

### Marketplace Rule
- Change marketplace rules or standards
- Update service requirements
- Modify marketplace policies

### Fee Structure
- Adjust escrow fees, bridge fees, trading fees
- Modify fee percentages
- Update fee calculation methods

### Service Approval
- Approve/reject software service types
- Add new service categories
- Remove deprecated services

### Protocol Upgrade
- Upgrade marketplace protocol or contracts
- Implement new features
- Fix critical bugs

### Dispute Resolution
- Resolve marketplace disputes
- Arbitrate conflicts
- Enforce decisions

### Parameter Change
- Adjust system parameters (timeouts, limits)
- Update configuration values
- Modify system constants

## Proposal Creation

### CLI Command

```bash
aitbc governance propose --type marketplace_rule --title "Adjust escrow fee" --description "Reduce escrow fee from 1% to 0.5%" --value 0.005
```

### Proposal Schema

```json
{
  "proposal_id": "prop_<uuid>",
  "proposer": "0x...",
  "type": "marketplace_rule|fee_structure|service_approval|protocol_upgrade|dispute_resolution|parameter_change",
  "title": "Adjust escrow fee",
  "description": "Reduce escrow fee from 1% to 0.5%",
  "value": 0.005,
  "status": "draft|active|passed|rejected|executed",
  "voting_start": "2026-06-03T...",
  "voting_end": "2026-06-10T...",
  "quorum_required": 1000000,
  "yes_votes": 0,
  "no_votes": 0,
  "created_at": "2026-06-03T..."
}
```

## Proposal Lifecycle

### 1. Draft
- Proposal created, not yet submitted
- Can be edited before submission
- Not visible to community

### 2. Active
- Voting period open
- Community can vote
- Cannot be edited

### 3. Passed
- Quorum met, majority yes
- Ready for execution
- Execution delay applies

### 4. Rejected
- Quorum not met or majority no
- Cannot be executed
- Can be resubmitted

### 5. Executed
- Proposal changes applied
- Changes live on network
- Cannot be reversed

## Software Marketplace Governance

### Service Approval

```bash
# Propose new service type
aitbc governance propose --type service_approval --title "Add image generation service" --description "Add Stable Diffusion as supported service type"
```

### Fee Governance

```bash
# Propose fee change
aitbc governance propose --type fee_structure --title "Reduce escrow fee" --value 0.005
```

### Dispute Resolution

```bash
# Propose dispute resolution
aitbc governance propose --type dispute_resolution --title "Resolve dispute job_123" --description "Provider claims job completed, buyer disputes"
```

## CLI Commands

### Proposal Management

```bash
# Create proposal
aitbc governance propose --type marketplace_rule --title "Adjust escrow fee" --description "Reduce escrow fee from 1% to 0.5%" --value 0.005

# List proposals
aitbc governance list --status active

# Get proposal details
aitbc governance get prop_abc123

# Execute passed proposal
aitbc governance execute prop_abc123
```

---

*Last Updated: 2026-06-07*
