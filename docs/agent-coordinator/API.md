# AITBC Agent Coordinator - API Reference

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
    "agent_id": "hermes-agent",
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
curl http://localhost:9001/agents/hermes-agent
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
curl -X PUT http://localhost:9001/agents/hermes-agent/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "busy",
    "load_metrics": {
      "active_connections": 5,
      "pending_tasks": 2
    }
  }'
```

## Task Management API

### Submit Task

Submit a task for distribution to agents.

**Endpoint:** `POST /tasks/submit`

**Request Body:**
```json
{
  "task_data": {
    "task_type": "string",
    "model": "string",
    "prompt": "string",
    "parameters": {"string": "any"}
  },
  "priority": "string (required)",
  "requirements": {
    "capabilities": ["string"],
    "agent_type": "string"
  }
}
```

**Parameters:**
- `task_data` (required): Object containing task information
- `priority` (required): Task priority (urgent, critical, high, normal, low)
- `requirements` (optional): Object specifying agent requirements

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Task submitted successfully",
  "task_id": "UUID string",
  "priority": "string",
  "submitted_at": "ISO 8601 timestamp"
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Invalid priority: {priority}"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Task distributor not available"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Error submitting task: {error message}"
}
```

**Example:**
```bash
curl -X POST http://localhost:9001/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "task_data": {
      "model": "llama2",
      "prompt": "test prompt"
    },
    "priority": "normal",
    "requirements": {}
  }'
```

### Get Task Status

Get task distribution statistics and load balancer metrics.

**Endpoint:** `GET /tasks/status`

**Response (200 OK):**
```json
{
  "status": "success",
  "stats": {
    "tasks_distributed": 0,
    "tasks_completed": 0,
    "tasks_failed": 0,
    "avg_distribution_time": 0.0,
    "load_balancer_stats": {
      "strategy": "least_connections",
      "total_assignments": 0,
      "successful_assignments": 0,
      "failed_assignments": 0,
      "success_rate": 0.0,
      "active_agents": 0,
      "agent_weights": 0,
      "avg_agent_load": 0
    },
    "queue_sizes": {
      "urgent": 0,
      "critical": 0,
      "high": 0,
      "normal": 0,
      "low": 0
    }
  },
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Task distributor not available"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Error getting task status: {error message}"
}
```

**Example:**
```bash
curl http://localhost:9001/tasks/status
```

## Health Check

### Service Health

Check the health of the agent coordinator service.

**Endpoint:** `GET /health`

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "string",
  "timestamp": "ISO 8601 timestamp"
}
```

**Example:**
```bash
curl http://localhost:9001/health
```

## Error Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource not found |
| 422 | Unprocessable Entity - Validation error |
| 500 | Internal Server Error |
| 503 | Service Unavailable - Component not ready |

## Rate Limiting

Currently, rate limiting is not implemented. Future versions may include rate limiting to prevent abuse.

## WebSocket Support

WebSocket support is planned for future releases to provide real-time updates on:
- Agent status changes
- Task distribution events
- Load balancer metrics updates

## OpenAPI Specification

The API follows OpenAPI 3.0 specification. An OpenAPI JSON schema can be generated from the FastAPI application by visiting:

```
http://localhost:9001/openapi.json
```

Interactive API documentation is available at:

```
http://localhost:9001/docs
```
