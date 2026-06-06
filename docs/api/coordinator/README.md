# Coordinator API

The Coordinator API is the central service for job submission, management, and coordination in the AITBC platform.

## Base URL

- Production: `https://aitbc.bubuit.net/api`
- Staging: `https://staging-api.aitbc.io`
- Development: `http://localhost:8203`

## Authentication

Most endpoints require an API key passed via the `X-Api-Key` header. API keys can be obtained by registering as a client.

## Endpoints

### Job Management

#### Submit Job
`POST /v1/jobs`

Submit a new compute job to the platform.

**Request Body:**
```json
{
  "payload": {
    "model": "string",
    "prompt": "string",
    "parameters": {}
  },
  "constraints": {
    "min_gpu_memory": 8,
    "gpu_type": "nvidia-rtx-3090"
  },
  "ttl_seconds": 900,
  "payment_amount": 100.0,
  "payment_currency": "AITBC"
}
```

**Response:** `201 Created`
```json
{
  "job_id": "string",
  "state": "QUEUED",
  "assigned_miner_id": null,
  "requested_at": "2026-05-11T10:00:00Z",
  "expires_at": "2026-05-11T10:15:00Z",
  "error": null,
  "payment_id": null,
  "payment_status": null
}
```

#### Get Job Status
`GET /v1/jobs/{job_id}`

Retrieve the current status of a job.

**Response:** `200 OK`
```json
{
  "job_id": "string",
  "state": "RUNNING",
  "assigned_miner_id": "miner-123",
  "requested_at": "2026-05-11T10:00:00Z",
  "expires_at": "2026-05-11T10:15:00Z",
  "error": null,
  "payment_id": "pay-456",
  "payment_status": "escrowed"
}
```

#### Get Job Result
`GET /v1/jobs/{job_id}/result`

Retrieve the result of a completed job.

**Response:** `200 OK`
```json
{
  "result": {
    "output": "string",
    "metadata": {}
  },
  "receipt": {
    "job_id": "string",
    "miner_id": "string",
    "signature": "string"
  }
}
```

#### Cancel Job
`POST /v1/jobs/{job_id}/cancel`

Cancel a queued or running job.

**Response:** `200 OK`
```json
{
  "job_id": "string",
  "state": "CANCELLED",
  "assigned_miner_id": "miner-123",
  "error": "Cancelled by user"
}
```

### Payment Management

#### Get Job Payment
`GET /v1/jobs/{job_id}/payment`

Retrieve payment information for a job.

**Response:** `200 OK`
```json
{
  "payment_id": "string",
  "job_id": "string",
  "amount": 100.0,
  "currency": "AITBC",
  "status": "released",
  "created_at": "2026-05-11T10:00:00Z"
}
```

### Receipt Management

#### Get Latest Receipt
`GET /v1/jobs/{job_id}/receipt`

Retrieve the latest signed receipt for a job.

**Response:** `200 OK`
```json
{
  "job_id": "string",
  "miner_id": "string",
  "signature": "string",
  "timestamp": "2026-05-11T10:05:00Z"
}
```

#### List All Receipts
`GET /v1/jobs/{job_id}/receipts`

Retrieve all signed receipts for a job.

**Response:** `200 OK`
```json
[
  {
    "job_id": "string",
    "miner_id": "string",
    "signature": "string",
    "timestamp": "2026-05-11T10:05:00Z"
  }
]
```

## Job States

Jobs transition through the following states:

- `QUEUED` - Job submitted, waiting for miner assignment
- `RUNNING` - Job assigned to miner, currently processing
- `COMPLETED` - Job finished successfully
- `FAILED` - Job failed with error
- `CANCELLED` - Job cancelled by user
- `EXPIRED` - Job exceeded TTL without completion

## Rate Limits

- Job submission: 100 requests per minute
- Job status queries: 1000 requests per minute
- Result retrieval: 500 requests per minute

## WebSocket

Real-time job status updates are available via WebSocket connection:

```
ws://localhost:8203/v1/jobs/{job_id}/ws
```

The WebSocket sends status updates as JSON messages:
```json
{
  "job_id": "string",
  "state": "RUNNING",
  "timestamp": "2026-05-11T10:05:00Z"
}
```

## Examples

### Python SDK

```python
import aitbc_sdk

client = aitbc_sdk.Client(api_key="your-api-key")

# Submit a job
job = client.submit_job(
    payload={"model": "llama2", "prompt": "Hello world"},
    ttl_seconds=900
)

# Check status
status = client.get_job(job.job_id)
print(f"Job state: {status.state}")

# Get result
result = client.get_job_result(job.job_id)
print(f"Result: {result.result}")
```

### cURL

```bash
# Submit job
curl -X POST http://localhost:8203/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-api-key" \
  -d '{
    "payload": {"model": "llama2", "prompt": "Hello world"},
    "ttl_seconds": 900
  }'

# Get status
curl http://localhost:8203/v1/jobs/{job_id} \
  -H "X-Api-Key: your-api-key"

# Get result
curl http://localhost:8203/v1/jobs/{job_id}/result \
  -H "X-Api-Key: your-api-key"
```

## OpenAPI Specification

The complete OpenAPI 3.1.0 specification is available in [openapi.json](./openapi.json).
