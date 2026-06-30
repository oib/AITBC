# Agent Coordinator API - Reference

**Last Updated**: 2026-06-30
**Version**: 1.0

## Base URL

```
http://localhost:9001
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

## Related Topics

- [Agent Management API](./api-agent-management.md) - Agent registration and discovery
- [Task Management API](./api-task-management.md) - Task submission and status
- [Message Management API](./api-message-management.md) - Agent messaging
- [Peer Management API](./api-peer-management.md) - Peer connections
