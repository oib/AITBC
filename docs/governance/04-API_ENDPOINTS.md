# API Endpoints

## Overview

The Governance Service exposes REST API endpoints for managing governance operations. All endpoints are prefixed with `/v1/governance/` except for health checks.

## Base URL

```
http://localhost:8105
```

## Core Endpoints

### Health Check

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "governance-service"
}
```

#### GET /ready
Readiness check - verifies database connectivity.

**Response:**
```json
{
  "status": "ready",
  "service": "governance-service"
}
```

#### GET /live
Liveness check - verifies service is not stuck.

**Response:**
```json
{
  "status": "alive",
  "service": "governance-service"
}
```

### Governance Status

#### GET /v1/governance/status
Get governance service status.

**Response:**
```json
{
  "status": "operational",
  "service": "governance-service",
  "message": "Governance service is running"
}
```

## Profile Endpoints

### List Profiles

#### GET /v1/governance/profiles
List governance profiles with optional filters.

**Query Parameters:**
- `role` (optional): Filter by role
- `user_id` (optional): Filter by user ID

**Response:**
```json
[
  {
    "profile_id": "uuid",
    "user_id": "user123",
    "role": "voter",
    "created_at": "2026-06-07T00:00:00Z",
    "updated_at": "2026-06-07T00:00:00Z"
  }
]
```

### Get Profile

#### GET /v1/governance/profiles/{profile_id}
Get a specific governance profile.

**Path Parameters:**
- `profile_id`: Profile UUID

**Response:**
```json
{
  "profile_id": "uuid",
  "user_id": "user123",
  "role": "voter",
  "created_at": "2026-06-07T00:00:00Z",
  "updated_at": "2026-06-07T00:00:00Z"
}
```

### Create Profile

#### POST /v1/governance/profiles
Create a new governance profile.

**Request Body:**
```json
{
  "user_id": "user123",
  "role": "voter"
}
```

**Response:**
```json
{
  "profile_id": "uuid",
  "user_id": "user123",
  "role": "voter",
  "created_at": "2026-06-07T00:00:00Z",
  "updated_at": "2026-06-07T00:00:00Z"
}
```

## Proposal Endpoints

### List Proposals

#### GET /v1/governance/proposals
List governance proposals with optional filters.

**Query Parameters:**
- `status` (optional): Filter by status (draft, active, succeeded, rejected, executed)
- `category` (optional): Filter by category
- `proposer_id` (optional): Filter by proposer ID

**Response:**
```json
[
  {
    "proposal_id": "uuid",
    "proposer_id": "user123",
    "title": "Test Proposal",
    "description": "Test description",
    "category": "general",
    "status": "active",
    "voting_starts": "2026-06-07T00:00:00Z",
    "voting_ends": "2026-06-14T00:00:00Z",
    "executed_at": null,
    "created_at": "2026-06-07T00:00:00Z",
    "updated_at": "2026-06-07T00:00:00Z"
  }
]
```

### Get Proposal

#### GET /v1/governance/proposals/{proposal_id}
Get a specific proposal.

**Path Parameters:**
- `proposal_id`: Proposal UUID

**Response:**
```json
{
  "proposal_id": "uuid",
  "proposer_id": "user123",
  "title": "Test Proposal",
  "description": "Test description",
  "category": "general",
  "status": "active",
  "voting_starts": "2026-06-07T00:00:00Z",
  "voting_ends": "2026-06-14T00:00:00Z",
  "executed_at": null,
  "created_at": "2026-06-07T00:00:00Z",
  "updated_at": "2026-06-07T00:00:00Z"
}
```

### Create Proposal

#### POST /v1/governance/proposals
Create a new governance proposal.

**Request Body:**
```json
{
  "proposer_id": "user123",
  "title": "Test Proposal",
  "description": "Test description",
  "category": "general",
  "voting_starts": "2026-06-07T00:00:00Z",
  "voting_ends": "2026-06-14T00:00:00Z"
}
```

**Response:**
```json
{
  "proposal_id": "uuid",
  "proposer_id": "user123",
  "title": "Test Proposal",
  "description": "Test description",
  "category": "general",
  "status": "active",
  "voting_starts": "2026-06-07T00:00:00Z",
  "voting_ends": "2026-06-14T00:00:00Z",
  "executed_at": null,
  "created_at": "2026-06-07T00:00:00Z",
  "updated_at": "2026-06-07T00:00:00Z"
}
```

### Execute Proposal (v0.4.12)

#### POST /v1/governance/proposals/{proposal_id}/execute
Execute a passed proposal with logging.

**Path Parameters:**
- `proposal_id`: Proposal UUID

**Response:**
```json
{
  "proposal_id": "uuid",
  "status": "executed",
  "executed_at": "2026-06-15T00:00:00Z"
}
```

**Error Responses:**
- 404: Proposal not found
- 400: Proposal not in succeeded state

## Vote Endpoints

### List Votes

#### GET /v1/governance/votes
List votes with optional filters.

**Query Parameters:**
- `proposal_id` (optional): Filter by proposal ID
- `voter_id` (optional): Filter by voter ID

**Response:**
```json
[
  {
    "vote_id": "uuid",
    "proposal_id": "proposal_uuid",
    "voter_id": "user123",
    "vote_type": "for",
    "voting_power": 1000,
    "reason": "Support this proposal",
    "created_at": "2026-06-07T00:00:00Z"
  }
]
```

### Create Vote

#### POST /v1/governance/votes
Create a new vote.

**Request Body:**
```json
{
  "proposal_id": "proposal_uuid",
  "voter_id": "user123",
  "vote_type": "for",
  "voting_power": 1000,
  "reason": "Support this proposal"
}
```

**Response:**
```json
{
  "vote_id": "uuid",
  "proposal_id": "proposal_uuid",
  "voter_id": "user123",
  "vote_type": "for",
  "voting_power": 1000,
  "reason": "Support this proposal",
  "created_at": "2026-06-07T00:00:00Z"
}
```

## v0.4.12 New Endpoints

### Stake Tokens

#### POST /v1/governance/stake
Stake tokens for enhanced voting power.

**Request Body:**
```json
{
  "staker_address": "0x1234567890abcdef",
  "amount": 1000,
  "lock_period_days": 30
}
```

**Response:**
```json
{
  "stake_id": "uuid",
  "staker_address": "0x1234567890abcdef",
  "amount_staked": 1000,
  "lock_period_days": 30,
  "unstakes_at": "2026-07-07T00:00:00Z",
  "voting_power": 2000
}
```

**Error Responses:**
- 500: Lock period must be at least 30 days

### Get Voting Power

#### GET /v1/governance/voting-power/{address}
Get voting power for an address.

**Path Parameters:**
- `address`: Wallet address

**Response:**
```json
{
  "address": "0x1234567890abcdef",
  "voting_power": 2000,
  "calculated_at": 1717756800
}
```

### Delegate Voting Power

#### POST /v1/governance/delegate
Delegate voting power to another address.

**Request Body:**
```json
{
  "delegator_address": "0x1234567890abcdef",
  "delegate_address": "0x0987654321fedcba",
  "amount": 500
}
```

**Response:**
```json
{
  "delegation_id": "uuid",
  "delegator_address": "0x1234567890abcdef",
  "delegate_address": "0x0987654321fedcba",
  "voting_power": 500,
  "created_at": "2026-06-07T00:00:00Z"
}
```

**Error Responses:**
- 500: Insufficient voting power

## Treasury & Analytics

### Get Treasury

#### GET /v1/governance/treasury
Get DAO treasury information.

**Response:**
```json
{
  "treasury_id": "main_treasury",
  "balance": 1000000.0,
  "last_updated": "2026-06-07T00:00:00Z"
}
```

### Get Analytics

#### GET /v1/governance/analytics
Get governance analytics.

**Query Parameters:**
- `period` (optional): Time period (default: monthly)

**Response:**
```json
{
  "period": "monthly",
  "total_proposals": 10,
  "active_proposals": 3,
  "passed_proposals": 5,
  "total_votes": 100
}
```

## Transaction Endpoints

### Submit Transaction

#### POST /v1/transactions
Submit a governance transaction.

**Request Body:**
```json
{
  "type": "governance",
  "action": "propose",
  "proposal_id": "prop_123",
  "title": "Test Proposal",
  "description": "Test description"
}
```

**Response:**
```json
{
  "status": "success",
  "transaction_id": "prop_123"
}
```

### Query Transactions

#### GET /v1/transactions
Query governance transactions.

**Query Parameters:**
- `transaction_type` (optional): Filter by type
- `action` (optional): Filter by action (propose, vote)
- `status` (optional): Filter by status
- `island_id` (optional): Filter by island ID

**Response:**
```json
[
  {
    "id": "prop_123",
    "action": "propose",
    "title": "Test Proposal",
    "status": "active",
    "created_at": "2026-06-07T00:00:00Z"
  }
]
```

## Error Responses

All endpoints may return error responses:

```json
{
  "error": "Error message"
}
```

**Common HTTP Status Codes:**
- 200: Success
- 400: Bad Request
- 404: Not Found
- 500: Internal Server Error

## Rate Limiting

Rate limiting is applied to prevent abuse:
- 100 requests per minute per IP
- 1000 requests per hour per IP

## Authentication

Service-to-service communication requires API key authentication via the `X-API-Key` header.

## CORS

CORS is enabled for cross-origin requests from the API Gateway.
