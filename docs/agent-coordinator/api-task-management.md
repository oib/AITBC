# Agent Coordinator API - Task Management

**Last Updated**: 2026-06-30
**Version**: 1.0

## Base URL

```
http://localhost:9001
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

## Related Topics

- [Agent Management API](./api-agent-management.md) - Agent registration and discovery
- [Message Management API](./api-message-management.md) - Agent messaging
- [Peer Management API](./api-peer-management.md) - Peer connections
- [API Reference](./api-reference.md) - Health checks, error codes, and OpenAPI
