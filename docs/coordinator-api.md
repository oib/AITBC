# Coordinator API - AITBC Documentation

FastAPI service for job submission, miner registration, and receipt management. SQLite persistence with comprehensive endpoints.

<span class="component-status live">● Live</span>

## Overview

The Coordinator API is the central orchestration layer that manages job distribution between clients and miners in the AITBC network. It handles job submissions, miner registrations, and tracks all computation receipts.

### Key Features

- Job submission and tracking
- Miner registration and heartbeat monitoring
- Receipt management and verification
- User management with wallet-based authentication
- SQLite persistence with SQLModel ORM
- Comprehensive API documentation with OpenAPI

## Architecture

The Coordinator API follows a clean architecture with separation of concerns for domain models, API routes, and business logic.

#### API Layer
FastAPI routers for clients, miners, admin, and users

#### Domain Models
SQLModel definitions for jobs, miners, receipts, users

#### Business Logic
Service layer handling job orchestration

#### Persistence
SQLite database with Alembic migrations

## API Reference

The Coordinator API provides RESTful endpoints for all major operations.

### Client Endpoints

`POST /v1/client/jobs`
Submit a new computation job

`GET /v1/client/jobs/{job_id}/status`
Get job status and progress

`GET /v1/client/jobs/{job_id}/receipts`
Retrieve computation receipts

### Miner Endpoints

`POST /v1/miner/register`
Register as a compute provider

`POST /v1/miner/heartbeat`
Send miner heartbeat

`GET /v1/miner/jobs`
Fetch available jobs

`POST /v1/miner/result`
Submit job result

### User Management

`POST /v1/users/login`
Login or register with wallet

`GET /v1/users/me`
Get current user profile

`GET /v1/users/{user_id}/balance`
Get user wallet balance

### Exchange Endpoints

`POST /v1/exchange/create-payment`
Create Bitcoin payment request

`GET /v1/exchange/payment-status/{id}`
Check payment status

## Authentication

The API uses API key authentication for clients and miners, and session-based authentication for users.

### API Keys

```http
X-Api-Key: your-api-key-here
```

### Session Tokens

```http
X-Session-Token: sha256-token-here
```

### Example Request

```bash
curl -X POST "https://aitbc.bubuit.net/api/v1/client/jobs" \
  -H "X-Api-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "llm_inference",
    "parameters": {...}
  }'
```

## Configuration

The Coordinator API can be configured via environment variables.

### Environment Variables

```bash
# Database
DATABASE_URL=sqlite:///coordinator.db

# API Settings
API_HOST=0.0.0.0
API_PORT=8000

# Security
SECRET_KEY=your-secret-key
API_KEYS=key1,key2,key3

# Exchange
BITCOIN_ADDRESS=tb1qxy2...
BTC_TO_AITBC_RATE=100000
```

## Deployment

The Coordinator API runs in a Docker container with nginx proxy.

### Docker Deployment

```bash
# Build image
docker build -t aitbc-coordinator .

# Run container
docker run -d \
  --name aitbc-coordinator \
  -p 8000:8000 \
  -e DATABASE_URL=sqlite:///data/coordinator.db \
  -v $(pwd)/data:/app/data \
  aitbc-coordinator
```

### Systemd Service

```bash
# Start service
sudo systemctl start aitbc-coordinator

# Check status
sudo systemctl status aitbc-coordinator

# View logs
sudo journalctl -u aitbc-coordinator -f
```

## Interactive API Documentation

Interactive API documentation is available via Swagger UI and ReDoc.

- [Swagger UI](https://aitbc.bubuit.net/api/docs)
- [ReDoc](https://aitbc.bubuit.net/api/redoc)
- [OpenAPI Spec](https://aitbc.bubuit.net/api/openapi.json)

## Data Models

### Job

```json
{
  "id": "uuid",
  "client_id": "string",
  "job_type": "llm_inference",
  "parameters": {},
  "status": "pending|running|completed|failed",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Miner

```json
{
  "id": "uuid",
  "address": "string",
  "endpoint": "string",
  "capabilities": [],
  "status": "active|inactive",
  "last_heartbeat": "timestamp"
}
```

### Receipt

```json
{
  "id": "uuid",
  "job_id": "uuid",
  "miner_id": "uuid",
  "result": {},
  "proof": "string",
  "created_at": "timestamp"
}
```

## Error Handling

The API returns standard HTTP status codes with detailed error messages:

```json
{
  "error": {
    "code": "INVALID_JOB_TYPE",
    "message": "The specified job type is not supported",
    "details": {}
  }
}
```

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

- Client endpoints: 100 requests/minute
- Miner endpoints: 1000 requests/minute
- User endpoints: 60 requests/minute

## Monitoring

The Coordinator API exposes metrics at `/metrics` endpoint:

- `api_requests_total` - Total API requests
- `api_request_duration_seconds` - Request latency
- `active_jobs` - Currently active jobs
- `registered_miners` - Number of registered miners

## Security

- All sensitive endpoints require authentication
- API keys should be kept confidential
- HTTPS is required in production
- Input validation on all endpoints
- SQL injection prevention via ORM
