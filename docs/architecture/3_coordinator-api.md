# Coordinator API - AITBC Documentation

FastAPI service for job submission, miner registration, and receipt management. SQLite persistence with comprehensive endpoints.

● Live

## Overview

The Coordinator API is the central orchestration layer that manages job distribution between clients and miners in the the network. It handles job submissions, miner registrations, and tracks all computation receipts.

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

The Coordinator API provides RESTful endpoints for all major operations. All business logic endpoints use the `/v1` prefix for consistent versioning.

### API Versioning Structure

- **Business logic endpoints**: `/v1/{endpoint}` — the client router mounts at the `/v1` root (e.g., `/v1/jobs`, `/v1/miners/register`)
- **Infrastructure endpoints**: No prefix (e.g., `/health`, `/metrics`, `/docs`) — for system operations

This structure enables future versioning (`/v2`, etc.) while maintaining CLI compatibility.

### Client Endpoints

`POST /v1/jobs`
Submit a new computation job (201 Created)

`GET /v1/jobs/{job_id}`
Get job status and progress

`GET /v1/jobs/{job_id}/result`
Get the job result

`POST /v1/jobs/{job_id}/cancel`
Cancel a job

`POST /v1/jobs/{job_id}/accept` / `POST /v1/jobs/{job_id}/reject`
Accept a result (release payment) or reject it (open dispute)

`GET /v1/jobs/{job_id}/receipt` / `GET /v1/jobs/{job_id}/receipts`
Latest signed receipt / list signed receipts

`GET /v1/jobs` / `GET /v1/jobs/history`
List jobs with filtering / job history

### Miner Endpoints

Miner paths are plural — `/v1/miners/*`:

`POST /v1/miners/register`
Register as a compute provider

`POST /v1/miners/heartbeat`
Send miner heartbeat

`POST /v1/miners/poll`
Poll for the next assigned job

`POST /v1/miners/{job_id}/result`
Submit job result

`POST /v1/miners/{job_id}/fail`
Submit job failure

`POST /v1/miners/{miner_id}/jobs` / `POST /v1/miners/{miner_id}/earnings`
List jobs / earnings for a miner

### User Management

`POST /v1/auth/nonce`
Request a wallet login nonce challenge

`POST /v1/register`
Register a user

`POST /v1/login`
Login or register with wallet (signed nonce challenge; returns a JWT `session_token`)

`GET /v1/users/me`
Get current user profile

`GET /v1/users/{user_id}/balance`
Get user wallet balance

`POST /v1/logout`
Log out (blocklist the JWT)

### GPU Marketplace Endpoints

`POST /v1/marketplace/gpu/register`
Register a GPU on the marketplace

`GET /v1/marketplace/gpu/list`
List available GPUs (filter by available, model, price, region)

`GET /v1/marketplace/gpu/{gpu_id}`
Get GPU details

`POST /v1/marketplace/gpu/{gpu_id}/book`
Book a GPU for a duration

`POST /v1/marketplace/gpu/{gpu_id}/release`
Release a booked GPU

`GET /v1/marketplace/gpu/{gpu_id}/reviews`
Get reviews for a GPU

`POST /v1/marketplace/gpu/{gpu_id}/reviews`
Add a review for a GPU

`GET /v1/marketplace/orders`
List marketplace orders

`GET /v1/marketplace/pricing/{model}`
Get pricing for a GPU model

### Payment Endpoints

`POST /v1/payments`
Create payment for a job

`GET /v1/payments/{payment_id}`
Get payment details

`GET /v1/jobs/{job_id}/payment`
Get payment for a job

`POST /v1/payments/{payment_id}/release`
Release payment from escrow

`POST /v1/payments/{payment_id}/refund`
Refund payment

`GET /v1/payments/{payment_id}/receipt`
Get payment receipt

### Governance Endpoints

The coordinator mounts a governance router at `/v1/governance`:

`POST /v1/governance/proposals`
Create a governance proposal (listing/details `GET` routes live on the standalone governance service, port 8105)

`POST /v1/governance/proposals/{proposal_id}/vote`
Submit a vote on a proposal

`POST /v1/governance/proposals/{proposal_id}/execute`
Execute an approved proposal

`POST /v1/governance/proposals/{proposal_id}/process`
Process a proposal tally

`POST /v1/governance/profiles` / `POST /v1/governance/profiles/{profile_id}/delegate`
Governance profiles / delegation

`POST /v1/governance/analytics/reports`
Transparency reports

> The **standalone governance service** (port 8105, `apps/governance/`) hosts the canonical proposal/vote/params surface: `GET|POST /v1/governance/proposals`, `POST /v1/governance/votes`, `GET /v1/governance/params`, `GET /v1/governance/voting-power/{address}`, plus close/propagate/aggregate-votes/execute-cross-chain. There is no `/v1/governance/parameters` or `/v1/governance/voting-power/*` on the coordinator — those are on 8105 (`/v1/governance/params`). Chain-side governance (`/rpc/governance/*` on the blockchain node) is `X-API-Key` gated.

### Explorer Endpoints

`GET /v1/explorer/blocks`
List recent blocks

`GET /v1/explorer/transactions`
List recent transactions

`GET /v1/explorer/addresses`
List address summaries

`GET /v1/explorer/receipts`
List job receipts

### Exchange Endpoints

`POST /v1/exchange/create-payment`
Create Ethereum deposit request

`GET /v1/exchange/payment-status/{id}`
Check payment status

## Authentication

The canonical customer credential is a **JWT bearer token** issued by the wallet-signed login flow (`POST /v1/auth/nonce` → `POST /v1/login` returns `session_token`). `X-Api-Key` remains for service/legacy callers — miner routes accept either via `require_miner` (Bearer JWT or `X-Api-Key`). There is no `X-Session-Token` header.

### Bearer JWT (canonical)

```http
Authorization: Bearer <jwt session_token>
```

### API Key (service / legacy / miner)

```http
X-Api-Key: <YOUR_API_KEY>
```

### Example Request

```bash
curl -X POST "http://localhost:8203/v1/jobs" \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {"model": "llama2", "prompt": "Hello"},
    "ttl_seconds": 900
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
API_PORT=8203

# Security
SECRET_KEY=<YOUR_SECRET_KEY>
API_KEYS=key1,key2,key3

# Exchange
ETHEREUM_ADDRESS=0x0000...
ETH_TO_AITBC_RATE=100000
```

## Deployment

The Coordinator API runs as a systemd service behind nginx.

### Systemd Service

```bash
# Start service
systemctl start aitbc-coordinator

# Check status
systemctl status aitbc-coordinator

# View logs
journalctl -u aitbc-coordinator -f
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
