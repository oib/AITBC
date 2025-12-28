---
title: Coordinator API Overview
description: Introduction to the AITBC Coordinator API
---

# Coordinator API Overview

The Coordinator API is the central service of the AITBC platform, responsible for job management, marketplace operations, and coordination between various components.

## Base URL

```
Production: https://aitbc.bubuit.net/api
Staging: https://staging-api.aitbc.io
Development: http://localhost:8011
```

## Authentication

All API endpoints require authentication using an API key. Include the API key in the request header:

```http
X-API-Key: your_api_key_here
```

Get your API key from the [AITBC Dashboard](https://dashboard.aitbc.io).

## Core Concepts

### Jobs
Jobs are the primary unit of work in AITBC. They represent AI computations that need to be executed.

```json
{
  "job_id": "job_1234567890",
  "type": "ai-inference",
  "status": "running",
  "created_at": "2024-01-01T12:00:00Z",
  "estimated_completion": "2024-01-01T12:05:00Z"
}
```

### Marketplace
The marketplace connects job creators with miners who can execute the jobs.

```json
{
  "offer_id": "offer_1234567890",
  "job_type": "image-classification",
  "price": "0.001",
  "miner_id": "miner_1234567890"
}
```

### Receipts
Receipts provide cryptographic proof of job execution and results.

```json
{
  "receipt_id": "receipt_1234567890",
  "job_id": "job_1234567890",
  "signature": {
    "sig": "base64_signature",
    "public_key": "base64_public_key"
  }
}
```

## Rate Limits

API requests are rate-limited to ensure fair usage:

| Plan | Requests per minute | Burst |
|------|---------------------|-------|
| Free | 60 | 10 |
| Pro | 600 | 100 |
| Enterprise | 6000 | 1000 |

## Error Handling

The API uses standard HTTP status codes and returns detailed error messages:

```json
{
  "error": {
    "code": "INVALID_API_KEY",
    "message": "The provided API key is invalid",
    "details": {
      "request_id": "req_1234567890"
    }
  }
}
```

Common error codes:
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Invalid or missing API key
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

## SDK Support

Official SDKs are available for:
- [Python](../../developer-guide/sdks/python.md)
- [JavaScript/TypeScript](../../developer-guide/sdks/javascript.md)

## WebSocket API

Real-time updates are available through WebSocket connections:

```javascript
const ws = new WebSocket('wss://aitbc.bubuit.net/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Job update:', data);
};
```

## OpenAPI Specification

The complete OpenAPI 3.0 specification is available:
- [View in Swagger UI](https://aitbc.bubuit.net/api/docs)
- [Download JSON](openapi.md)

## Getting Started

1. [Get an API key](https://dashboard.aitbc.io/api-keys)
2. [Review authentication](authentication.md)
3. [Explore endpoints](endpoints.md)
4. [Check examples](../../developer-guide/examples.md)

## Support

- 📖 [Documentation](../../)
- 💬 [Discord](https://discord.gg/aitbc)
- 🐛 [Report Issues](https://github.com/aitbc/issues)
- 📧 [api-support@aitbc.io](mailto:api-support@aitbc.io)
