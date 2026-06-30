# Agent Coordinator API - Message Management

**Last Updated**: 2026-06-30
**Version**: 1.0

## Base URL

```
http://localhost:9001
```

## Message Management API

### Send Message

Send a message to a specific agent using a specified communication protocol.

**Endpoint:** `POST /messages/send`

**Request Body:**
```json
{
  "receiver_id": "string (required)",
  "message_type": "string (required)",
  "payload": {"string": "any"},
  "priority": "string (default: normal)",
  "protocol": "string (default: hierarchical)"
}
```

**Parameters:**
- `receiver_id` (required): Target agent ID
- `message_type` (required): Message type (direct, broadcast, hierarchical, peer_to_peer, etc.)
- `payload` (required): Message data
- `priority` (optional): Message priority (low, normal, high, critical)
- `protocol` (optional): Communication protocol (hierarchical, peer_to_peer, broadcast)

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Message sent successfully",
  "message_id": "UUID string",
  "receiver_id": "string",
  "protocol": "string",
  "sent_at": "ISO 8601 timestamp"
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Invalid protocol: {protocol}. Valid protocols: hierarchical, peer_to_peer, broadcast"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Communication manager not available"
}
```

**Example:**
```bash
curl -X POST http://localhost:9001/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "receiver_id": "agent-agent",
    "message_type": "direct",
    "payload": {"task": "process_data"},
    "priority": "normal",
    "protocol": "hierarchical"
  }'
```

### Broadcast Message

Broadcast a message to multiple agents with optional filtering.

**Endpoint:** `POST /messages/broadcast`

**Request Body:**
```json
{
  "message_type": "string (required)",
  "payload": {"string": "any"},
  "priority": "string (default: normal)",
  "agent_type": "string (optional)",
  "capabilities": ["string (optional)"]
}
```

**Parameters:**
- `message_type` (required): Message type
- `payload` (required): Message data
- `priority` (optional): Message priority (low, normal, high, critical)
- `agent_type` (optional): Filter by agent type
- `capabilities` (optional): Filter by capabilities

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Broadcast sent to {count} agents",
  "recipients": ["string"],
  "count": 0,
  "broadcast_at": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Communication manager not available"
}
```

**Example:**
```bash
curl -X POST http://localhost:9001/messages/broadcast \
  -H "Content-Type: application/json" \
  -d '{
    "message_type": "broadcast",
    "payload": {"announcement": "system_update"},
    "agent_type": "worker"
  }'
```

### Get Message History

Retrieve message history with optional filtering.

**Endpoint:** `GET /messages/history`

**Query Parameters:**
- `sender_id` (optional): Filter by sender ID
- `receiver_id` (optional): Filter by receiver ID
- `limit` (optional): Maximum number of messages (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response (200 OK):**
```json
{
  "status": "success",
  "messages": [
    {
      "message_id": "string",
      "sender_id": "string",
      "receiver_id": "string",
      "message_type": "string",
      "priority": "string",
      "payload": {"string": "any"},
      "protocol": "string",
      "timestamp": "ISO 8601 timestamp"
    }
  ],
  "count": 0,
  "limit": 100,
  "offset": 0,
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Message storage not available"
}
```

**Example:**
```bash
curl "http://localhost:9001/messages/history?sender_id=agent-1&limit=50"
```

### Get Specific Message

Retrieve a specific message by ID.

**Endpoint:** `GET /messages/{message_id}`

**URL Parameters:**
- `message_id` (required): The unique message identifier

**Response (200 OK):**
```json
{
  "status": "success",
  "message": {
    "message_id": "string",
    "sender_id": "string",
    "receiver_id": "string",
    "message_type": "string",
    "priority": "string",
    "payload": {"string": "any"},
    "protocol": "string",
    "timestamp": "ISO 8601 timestamp"
  },
  "timestamp": "ISO 8601 timestamp"
}
```

**Response (404 Not Found):**
```json
{
  "detail": "Message {message_id} not found"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Message storage not available"
}
```

**Example:**
```bash
curl http://localhost:9001/messages/{message_id}
```

## Related Topics

- [Agent Management API](./api-agent-management.md) - Agent registration and discovery
- [Task Management API](./api-task-management.md) - Task submission and status
- [Peer Management API](./api-peer-management.md) - Peer connections
- [API Reference](./api-reference.md) - Health checks, error codes, and OpenAPI
