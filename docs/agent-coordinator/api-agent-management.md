# Agent Coordinator API - Agent Management

**Last Updated**: 2026-06-30
**Version**: 1.0

## Base URL

```
http://localhost:9001
```

## Authentication

Currently, the API does not require authentication. Future versions may support API key authentication and JWT tokens.

## Agent Management API

### Register Agent

Register a new agent with the coordinator.

**Endpoint:** `POST /agents/register`

**Request Body:**
```json
{
  "agent_id": "string (required)",
  "agent_type": "string (required)",
  "capabilities": ["string"],
  "services": ["string"],
  "endpoints": {"string": "string"},
  "metadata": {"string": "any"}
}
```

**Parameters:**
- `agent_id` (required): Unique identifier for the agent
- `agent_type` (required): Type of agent (worker, provider, consumer, general)
- `capabilities` (optional): Array of agent capabilities
- `services` (optional): Array of available services
- `endpoints` (optional): Object mapping service names to URLs
- `metadata` (optional): Additional metadata as key-value pairs

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Agent {agent_id} registered successfully",
  "agent_id": "string",
  "registered_at": "ISO 8601 timestamp"
}
```

**Response (422 Unprocessable Entity):**
```json
{
  "detail": "Validation error message"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Failed to register agent: {error message}"
}
```

**Example:**
```bash
curl -X POST http://localhost:9001/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-agent",
    "agent_type": "worker",
    "capabilities": ["data-processing", "analysis"],
    "services": ["task-execution"],
    "endpoints": {"http": "http://localhost:9002"},
    "metadata": {"version": "1.0.0"}
  }'
```

### Discover Agents

Discover agents based on filtering criteria.

**Endpoint:** `POST /agents/discover`

**Request Body:**
```json
{
  "status": "string (optional)",
  "agent_type": "string (optional)",
  "capabilities": ["string (optional)"],
  "services": ["string (optional)"]
}
```

**Parameters:**
- `status` (optional): Filter by agent status (active, inactive, busy, stale)
- `agent_type` (optional): Filter by agent type
- `capabilities` (optional): Filter by required capabilities
- `services` (optional): Filter by available services

**Response (200 OK):**
```json
{
  "status": "success",
  "query": {},
  "agents": [
    {
      "agent_id": "string",
      "agent_type": "string",
      "status": "string",
      "capabilities": ["string"],
      "services": ["string"],
      "endpoints": {"string": "string"},
      "metadata": {"string": "any"},
      "last_heartbeat": "ISO 8601 timestamp",
      "registration_time": "ISO 8601 timestamp",
      "load_metrics": {"string": "number"},
      "health_score": 0.0-1.0,
      "version": "string",
      "tags": ["string"]
    }
  ],
  "count": 0,
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Error discovering agents: {error message}"
}
```

**Example:**
```bash
curl -X POST http://localhost:9001/agents/discover \
  -H "Content-Type: application/json" \
  -d '{
    "status": "active",
    "agent_type": "worker"
  }'
```

### Get Agent Information

Retrieve detailed information about a specific agent.

**Endpoint:** `GET /agents/{agent_id}`

**URL Parameters:**
- `agent_id` (required): The unique identifier of the agent

**Response (200 OK):**
```json
{
  "status": "success",
  "agent": {
    "agent_id": "string",
    "agent_type": "string",
    "status": "string",
    "capabilities": ["string"],
    "services": ["string"],
    "endpoints": {"string": "string"},
    "metadata": {"string": "any"},
    "last_heartbeat": "ISO 8601 timestamp",
    "registration_time": "ISO 8601 timestamp",
    "load_metrics": {"string": "number"},
    "health_score": 0.0-1.0,
    "version": "string",
    "tags": ["string"]
  },
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (404 Not Found):**
```json
{
  "detail": "Agent not found"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Error getting agent: {error message}"
}
```

**Example:**
```bash
curl http://localhost:9001/agents/agent-agent
```

### Update Agent Status

Update the status and load metrics of an agent.

**Endpoint:** `PUT /agents/{agent_id}/status`

**URL Parameters:**
- `agent_id` (required): The unique identifier of the agent

**Request Body:**
```json
{
  "status": "string (required)",
  "load_metrics": {
    "active_connections": 0,
    "pending_tasks": 0,
    "cpu_usage": 0.0,
    "memory_usage": 0.0
  }
}
```

**Parameters:**
- `status` (required): New agent status (active, inactive, busy, stale)
- `load_metrics` (optional): Object containing load metrics

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Agent {agent_id} status updated",
  "agent_id": "string",
  "new_status": "string",
  "updated_at": "ISO 8601 timestamp"
}
```

**Response (422 Unprocessable Entity):**
```json
{
  "detail": "Validation error message"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Error updating agent status: {error message}"
}
```

**Example:**
```bash
curl -X PUT http://localhost:9001/agents/agent-agent/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "busy",
    "load_metrics": {
      "active_connections": 5,
      "pending_tasks": 2
    }
  }'
```

## Related Topics

- [Task Management API](./api-task-management.md) - Task submission and status
- [Message Management API](./api-message-management.md) - Agent messaging
- [Peer Management API](./api-peer-management.md) - Peer connections
- [API Reference](./api-reference.md) - Health checks, error codes, and OpenAPI
