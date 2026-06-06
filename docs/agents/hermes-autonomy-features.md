# Hermes Agent Autonomy Features

**Last Updated:** June 5, 2026  
**Version:** v0.4.3.3 (Service Status Update)

This document describes the enhanced Hermes agent autonomy features for distributed decision making, self-healing, and autonomous resource management.

> **🟢 Operational Status**: All Hermes messaging systems are operational with AgentDaemon successfully polling every 10 seconds and Coordinator API responding normally.

## Overview

Hermes agents now have enhanced autonomy capabilities:

- **Distributed Decision Making**: Consensus-based voting with weighted decisions
- **Self-Healing and Error Recovery**: Automatic error detection and recovery mechanisms
- **Autonomous Resource Management**: Dynamic resource allocation and pricing

## API Endpoints

All endpoints are available at `http://localhost:8203/v1/hermes/*` and require admin API key authentication via the `X-Api-Key` header.

### Distributed Decision Making

#### Propose Decision
**POST** `/v1/hermes/decision/propose`

Create a new decision proposal for agent voting.

**Request Body:**
```json
{
  "decision_type": "resource_allocation",
  "title": "Increase GPU pricing",
  "description": "Should we increase GPU pricing by 20% due to high demand?",
  "proposed_by": "agent-123",
  "voting_deadline": "2026-06-02T11:00:00Z",
  "min_participation": 0.5,
  "required_approval": 0.6,
  "metadata": {}
}
```

**Valid Decision Types:**
- `resource_allocation` - Resource allocation decisions
- `pricing_adjustment` - Pricing adjustment decisions
- `task_assignment` - Task assignment decisions
- `consensus_vote` - General consensus votes
- `emergency_response` - Emergency response decisions

**Response:**
```json
{
  "decision_id": "uuid",
  "status": "pending",
  "created_at": "2026-06-02T10:00:00Z",
  "voting_deadline": "2026-06-02T11:00:00Z",
  "message": "Decision proposal created successfully"
}
```

#### Submit Vote
**POST** `/v1/hermes/decision/vote`

Submit an agent vote on a decision.

**Request Body:**
```json
{
  "decision_id": "uuid",
  "agent_id": "agent-456",
  "vote": "approve",
  "weight": 1.5,
  "reason": "Current market conditions justify price increase"
}
```

**Valid Vote Options:**
- `approve` - Approve the decision
- `reject` - Reject the decision
- `abstain` - Abstain from voting

**Response:**
```json
{
  "vote_id": "uuid",
  "decision_id": "uuid",
  "status": "success",
  "message": "Vote submitted successfully"
}
```

#### Get Decision Result
**GET** `/v1/hermes/decision/{decision_id}`

Get the current result of a decision.

**Response:**
```json
{
  "decision_id": "uuid",
  "status": "approved",
  "total_votes": 10,
  "approve_votes": 7,
  "reject_votes": 2,
  "abstain_votes": 1,
  "weighted_approve": 8.5,
  "weighted_reject": 2.0,
  "weighted_abstain": 1.0,
  "participation_rate": 0.8,
  "approval_rate": 0.81,
  "final_decision": "approve",
  "concluded_at": "2026-06-02T10:30:00Z"
}
```

#### List Decisions
**GET** `/v1/hermes/decision/`

List all decisions with optional filtering.

**Query Parameters:**
- `decision_type` (optional) - Filter by decision type
- `status` (optional) - Filter by status

**Response:**
```json
{
  "decisions": [...],
  "total": 5
}
```

### Self-Healing and Error Recovery

#### Report Health
**POST** `/v1/hermes/health/report`

Report health status for an agent or service.

**Request Body:**
```json
{
  "agent_id": "agent-123",
  "service_name": "gpu-service",
  "status": "healthy",
  "timestamp": "2026-06-02T10:00:00Z",
  "response_time_ms": 45.0,
  "error_message": null,
  "metadata": {}
}
```

**Valid Health Status:**
- `healthy` - Service is operating normally
- `degraded` - Service is degraded but functional
- `unhealthy` - Service is not functioning
- `recovering` - Service is in recovery process

**Response:**
```json
{
  "status": "success",
  "key": "agent-123:gpu-service"
}
```

#### Report Error
**POST** `/v1/hermes/health/error`

Report an error for self-healing analysis.

**Request Body:**
```json
{
  "agent_id": "agent-123",
  "service_name": "blockchain-node",
  "error_type": "network_error",
  "severity": "high",
  "error_message": "Network timeout occurred when connecting to blockchain node",
  "timestamp": "2026-06-02T10:00:00Z",
  "context": {
    "retry_attempt": 3
  }
}
```

**Valid Error Types:**
- `network_error` - Network-related errors
- `timeout_error` - Timeout errors
- `authentication_error` - Authentication failures
- `resource_error` - Resource allocation errors
- `service_unavailable` - Service unavailable errors
- `database_error` - Database errors
- `unknown_error` - Unknown errors

**Valid Severity Levels:**
- `low` - Low severity
- `medium` - Medium severity
- `high` - High severity
- `critical` - Critical severity

**Response:**
```json
{
  "status": "success",
  "error_id": "uuid"
}
```

#### Get Health Status
**GET** `/v1/hermes/health/status`

Get health status with optional filtering.

**Query Parameters:**
- `agent_id` (optional) - Filter by agent ID
- `service_name` (optional) - Filter by service name

**Response:**
```json
[
  {
    "agent_id": "agent-123",
    "service_name": "gpu-service",
    "status": "healthy",
    "timestamp": "2026-06-02T10:00:00Z",
    "response_time_ms": 45.0,
    "error_message": null,
    "metadata": {}
  }
]
```

#### Get Recovery History
**GET** `/v1/hermes/health/recovery-history`

Get recovery history with optional filtering.

**Query Parameters:**
- `agent_id` (optional) - Filter by agent ID
- `limit` (optional) - Maximum number of results (default: 100)

**Response:**
```json
[
  {
    "action_id": "uuid",
    "agent_id": "agent-123",
    "success": true,
    "message": "Recovery action restart_service executed successfully",
    "timestamp": "2026-06-02T10:05:00Z"
  }
]
```

### Autonomous Resource Management

#### Register Resource
**POST** `/v1/hermes/resource/register`

Register a new resource for autonomous management.

**Request Body:**
```json
{
  "resource_id": "GPU-A100-001",
  "resource_type": "gpu",
  "agent_id": "agent-123",
  "status": "available",
  "capacity": 100.0,
  "allocated": 0.0,
  "utilization": 0.0,
  "metadata": {
    "memory_gb": 40,
    "model": "A100"
  }
}
```

**Valid Resource Types:**
- `gpu` - GPU resources
- `cpu` - CPU resources
- `memory` - Memory resources
- `storage` - Storage resources
- `network` - Network resources

**Valid Resource Status:**
- `available` - Resource is available for allocation
- `allocated` - Resource is fully allocated
- `reserved` - Resource is reserved
- `maintenance` - Resource is under maintenance
- `offline` - Resource is offline

**Response:**
```json
{
  "status": "success",
  "resource_id": "GPU-A100-001"
}
```

#### Allocate Resource
**POST** `/v1/hermes/resource/allocate`

Allocate resources based on strategy.

**Request Body:**
```json
{
  "resource_type": "gpu",
  "agent_id": "agent-456",
  "required_capacity": 20.0,
  "strategy": "demand_based",
  "priority": 8,
  "duration_hours": 4.0,
  "metadata": {
    "task": "inference"
  }
}
```

**Valid Allocation Strategies:**
- `demand_based` - Allocate based on demand (default)
- `priority_based` - Allocate based on priority
- `round_robin` - Round-robin allocation
- `least_loaded` - Allocate to least loaded resource

**Response:**
```json
{
  "allocation_id": "uuid",
  "resource_id": "GPU-A100-001",
  "allocated_capacity": 20.0,
  "status": "success",
  "message": "Resource allocated successfully",
  "expires_at": "2026-06-02T14:00:00Z"
}
```

#### Release Resource
**POST** `/v1/hermes/resource/release`

Release allocated resources.

**Request Body:**
```json
{
  "allocation_id": "uuid",
  "agent_id": "agent-456"
}
```

**Response:**
```json
{
  "allocation_id": "uuid",
  "status": "success",
  "message": "Resource released successfully",
  "released_capacity": 20.0
}
```

#### Adjust Pricing
**POST** `/v1/hermes/resource/pricing/adjust`

Automatically adjust pricing based on utilization.

**Request Body:**
```json
{
  "resource_type": "gpu"
}
```

**Response:**
```json
{
  "resource_id": "gpu:pool",
  "current_price": 0.1,
  "new_price": 0.12,
  "adjustment_factor": 1.2,
  "reason": "High utilization (>80%)",
  "timestamp": "2026-06-02T10:00:00Z"
}
```

**Pricing Logic:**
- Utilization > 80%: Increase price by 20%
- Utilization > 60%: Increase price by 10%
- Utilization < 30%: Decrease price by 10%
- Otherwise: No change

#### Get Resource Pools
**GET** `/v1/hermes/resource/pools`

Get all resource pools.

**Response:**
```json
[
  {
    "pool_id": "gpu:pool",
    "resource_type": "gpu",
    "total_capacity": 500.0,
    "available_capacity": 300.0,
    "allocated_capacity": 200.0,
    "average_utilization": 0.4,
    "pricing": 0.1
  }
]
```

#### Get Allocations
**GET** `/v1/hermes/resource/allocations`

Get allocations with optional filtering.

**Query Parameters:**
- `agent_id` (optional) - Filter by agent ID

**Response:**
```json
[
  {
    "allocation_id": "uuid",
    "resource_id": "GPU-A100-001",
    "agent_id": "agent-456",
    "capacity": 20.0,
    "allocated_at": "2026-06-02T10:00:00Z",
    "expires_at": "2026-06-02T14:00:00Z",
    "strategy": "demand_based",
    "priority": 8
  }
]
```

## Example Usage

### Example 1: Distributed Decision Making

```bash
# Propose a decision
curl -X POST http://localhost:8203/v1/hermes/decision/propose \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "decision_type": "pricing_adjustment",
    "title": "Increase GPU pricing",
    "description": "Should we increase GPU pricing by 20% due to high demand?",
    "proposed_by": "agent-123",
    "voting_deadline": "2026-06-02T11:00:00Z",
    "min_participation": 0.5,
    "required_approval": 0.6
  }'

# Submit a vote
curl -X POST http://localhost:8203/v1/hermes/decision/vote \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "decision_id": "uuid-from-proposal",
    "agent_id": "agent-456",
    "vote": "approve",
    "weight": 1.5,
    "reason": "Market conditions justify price increase"
  }'

# Check decision result
curl -X GET http://localhost:8203/v1/hermes/decision/uuid-from-proposal \
  -H "X-Api-Key: YOUR_API_KEY"
```

### Example 2: Self-Healing

```bash
# Report health status
curl -X POST http://localhost:8203/v1/hermes/health/report \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "agent_id": "agent-123",
    "service_name": "gpu-service",
    "status": "degraded",
    "timestamp": "2026-06-02T10:00:00Z",
    "response_time_ms": 1200.0
  }'

# Report error
curl -X POST http://localhost:8203/v1/hermes/health/error \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "agent_id": "agent-123",
    "service_name": "blockchain-node",
    "error_type": "network_error",
    "severity": "high",
    "error_message": "Network timeout occurred",
    "context": {"retry_attempt": 3}
  }'

# Check recovery history
curl -X GET "http://localhost:8203/v1/hermes/health/recovery-history?agent_id=agent-123" \
  -H "X-Api-Key: YOUR_API_KEY"
```

### Example 3: Resource Management

```bash
# Register a GPU resource
curl -X POST http://localhost:8203/v1/hermes/resource/register \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "resource_id": "GPU-A100-001",
    "resource_type": "gpu",
    "agent_id": "agent-123",
    "status": "available",
    "capacity": 100.0,
    "metadata": {"memory_gb": 40, "model": "A100"}
  }'

# Allocate resources
curl -X POST http://localhost:8203/v1/hermes/resource/allocate \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "resource_type": "gpu",
    "agent_id": "agent-456",
    "required_capacity": 20.0,
    "strategy": "demand_based",
    "priority": 8,
    "duration_hours": 4.0
  }'

# Release resources
curl -X POST http://localhost:8203/v1/hermes/resource/release \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "allocation_id": "uuid-from-allocation",
    "agent_id": "agent-456"
  }'

# Adjust pricing
curl -X POST http://localhost:8203/v1/hermes/resource/pricing/adjust \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -d '{
    "resource_type": "gpu"
  }'

# View resource pools
curl -X GET http://localhost:8203/v1/hermes/resource/pools \
  -H "X-Api-Key: YOUR_API_KEY"
```

## Rate Limiting

All endpoints have rate limiting applied:

- Decision propose: 10 requests per minute
- Decision vote: 30 requests per minute
- Decision queries: 50 requests per minute
- Health report: 30 requests per minute
- Health error: 20 requests per minute
- Health queries: 50 requests per minute
- Resource register: 10 requests per minute
- Resource allocate: 20 requests per minute
- Resource release: 20 requests per minute
- Pricing adjust: 5 requests per minute
- Resource queries: 30 requests per minute

## Implementation Notes

- All services use in-memory storage for demonstration (replace with database in production)
- Self-healing actions are simulated (implement actual recovery logic in production)
- Pricing adjustments are automatic based on utilization thresholds
- Decision voting uses weighted voting with configurable thresholds
- Health monitoring triggers self-healing for degraded/unhealthy status and high/critical errors

## Related Documentation

- [Hermes Agent Documentation](compute-provider.md)
- [Marketplace API](../api/marketplace-api.md)
- [Security Hardening](../infrastructure/NETWORK_SECURITY_RECOMMENDATIONS.md)
- [Release Notes v0.4.3](../releases/RELEASE_v0.4.3.md)
