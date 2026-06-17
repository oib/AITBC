# Governance API - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces REST API endpoints for governance operations, including proposal management, voting, delegation, staking, and rewards.

## REST Endpoints

### Proposal Management

```
POST /v1/governance/proposals           # Create proposal
GET  /v1/governance/proposals           # List proposals
GET  /v1/governance/proposals/{id}      # Get proposal
POST /v1/governance/proposals/{id}/vote # Vote on proposal
POST /v1/governance/proposals/{id}/execute # Execute proposal
```

### Voting and Delegation

```
POST /v1/governance/delegate            # Delegate voting power
GET  /v1/governance/voting-power        # Get voting power
```

### Token Management

```
POST /v1/governance/stake               # Stake tokens
POST /v1/governance/unstake             # Unstake tokens
GET  /v1/governance/rewards             # Get rewards
POST /v1/governance/rewards/claim       # Claim rewards
```

## New Endpoints in v0.4.12

- `POST /v1/governance/stake` - Stake tokens for enhanced voting power
- `POST /v1/governance/delegate` - Delegate voting power
- `POST /v1/governance/proposals/{id}/execute` - Execute passed proposal
- `GET /v1/governance/voting-power` - Get voting power for an address

---

*Last Updated: 2026-06-07*
