# Agent Coordinator API - Peer Management

**Last Updated**: 2026-06-30
**Version**: 1.0

## Base URL

```
http://localhost:9001
```

## Peer Management API

### Add Peer Connection

Add a peer connection for an agent.

**Endpoint:** `POST /peers/add`

**Query Parameters:**
- `agent_id` (required): Agent ID
- `peer_id` (required): Peer agent ID

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Peer {peer_id} added for agent {agent_id}",
  "agent_id": "string",
  "peer_id": "string",
  "connected_at": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Peer storage not available"
}
```

**Example:**
```bash
curl -X POST "http://localhost:9001/peers/add?agent_id=agent-1&peer_id=agent-2"
```

### Remove Peer Connection

Remove a peer connection for an agent.

**Endpoint:** `POST /peers/remove`

**Query Parameters:**
- `agent_id` (required): Agent ID
- `peer_id` (required): Peer agent ID

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Peer {peer_id} removed for agent {agent_id}",
  "agent_id": "string",
  "peer_id": "string",
  "removed_at": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Peer storage not available"
}
```

**Example:**
```bash
curl -X POST "http://localhost:9001/peers/remove?agent_id=agent-1&peer_id=agent-2"
```

### Get Agent Peers

Get all peers for a specific agent.

**Endpoint:** `GET /peers/{agent_id}`

**URL Parameters:**
- `agent_id` (required): Agent ID

**Response (200 OK):**
```json
{
  "status": "success",
  "agent_id": "string",
  "peers": ["string"],
  "count": 0,
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Peer storage not available"
}
```

**Example:**
```bash
curl http://localhost:9001/peers/agent-1
```

### Get All Peer Connections

Get all peer connections in the system.

**Endpoint:** `GET /peers`

**Response (200 OK):**
```json
{
  "status": "success",
  "connections": {
    "agent_id": ["peer_id", ...],
    ...
  },
  "total_agents": 0,
  "total_peers": 0,
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Peer storage not available"
}
```

**Example:**
```bash
curl http://localhost:9001/peers
```

## Related Topics

- [Agent Management API](./api-agent-management.md) - Agent registration and discovery
- [Task Management API](./api-task-management.md) - Task submission and status
- [Message Management API](./api-message-management.md) - Agent messaging
- [API Reference](./api-reference.md) - Health checks, error codes, and OpenAPI
