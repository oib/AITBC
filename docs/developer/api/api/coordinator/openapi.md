---
title: OpenAPI Specification
description: Complete OpenAPI specification for the Coordinator API
---

# OpenAPI Specification

The complete OpenAPI 3.0 specification for the AITBC Coordinator API is available below.

## Interactive Documentation

- [Swagger UI](https://api.aitbc.io/docs) - Interactive API explorer
- [ReDoc](https://api.aitbc.io/redoc) - Alternative documentation view

## Download Specification

- [JSON Format](openapi.json) - Raw OpenAPI JSON
- [YAML Format](openapi.yaml) - OpenAPI YAML format

## Key Endpoints

### Jobs
- `POST /v1/jobs` - Create a new job
- `GET /v1/jobs/{job_id}` - Get job details
- `GET /v1/jobs` - List jobs
- `DELETE /v1/jobs/{job_id}` - Cancel job
- `GET /v1/jobs/{job_id}/results` - Get job results

### Marketplace
- `POST /v1/marketplace/offers` - Create offer
- `GET /v1/marketplace/offers` - List offers
- `POST /v1/marketplace/offers/{offer_id}/accept` - Accept offer

### Receipts
- `GET /v1/receipts/{job_id}` - Get receipt
- `POST /v1/receipts/verify` - Verify receipt

### Analytics
- `GET /v1/marketplace/stats` - Get marketplace statistics
- `GET /v1/miners/{miner_id}/stats` - Get miner statistics

## Authentication

All endpoints require authentication via the `X-API-Key` header.

## Rate Limits

API requests are rate-limited based on your subscription plan.

## WebSocket API

Real-time updates available at:
- WebSocket: `wss://api.aitbc.io/ws`
- Message types: job_update, marketplace_update, receipt_created

## Code Generation

Use the OpenAPI spec to generate client libraries:

```bash
# OpenAPI Generator
openapi-generator-cli generate -i openapi.json -g python -o ./client/

# Or use the online generator at https://openapi-generator.tech/
```

## SDK Integration

The OpenAPI spec is integrated into our official SDKs:
- [Python SDK](../../developer-guide/sdks/python.md)
- [JavaScript SDK](../../developer-guide/sdks/javascript.md)

## Support

For API support:
- 📖 [API Documentation](endpoints.md)
- 🐛 [Report Issues](https://github.com/aitbc/issues)
- 💬 [Discord](https://discord.gg/aitbc)
- 📧 [api-support@aitbc.io](mailto:api-support@aitbc.io)
