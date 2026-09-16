# Agent Coordinator API - Reference

**Last Updated**: 2026-06-30
**Version**: 1.0

## Base URL

```
http://localhost:8107
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
curl http://localhost:8107/health
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

Per-route rate limits are enforced via `aitbc.rate_limiting.rate_limit`:

- `POST /api/v1/agent/messages/send` — 50/min
- inbox/history/discover/task-submit routes — 50–200/min (see per-route
  decorators in `routers/`)

Exceeding a limit returns `429`.

## WebSocket Support

Implemented — two streams under `/api/v1/agent/` (nginx-proxied at
`/agent/api/v1/agent/` on the hub):

- `WS /api/v1/agent/messages/stream` — real-time agent messaging
- `WS /api/v1/agent/presence/stream` — presence/tracking updates
- `GET /api/v1/agent/ws/status` — WebSocket layer status (auth-gated)

See `routers/websocket.py` for the handshake and auth requirements.

## OpenAPI Specification

The API follows OpenAPI 3.0 specification. An OpenAPI JSON schema can be generated from the FastAPI application by visiting:

```
http://localhost:8107/openapi.json
```

Interactive API documentation is available at:

```
http://localhost:8107/docs
```

## Related Topics

- [Agent Management API](./api-agent-management.md) - Agent registration and discovery
- [Task Management API](./api-task-management.md) - Task submission and status
- [Message Management API](./api-message-management.md) - Agent messaging
- [Peer Management API](./api-peer-management.md) - Peer connections
