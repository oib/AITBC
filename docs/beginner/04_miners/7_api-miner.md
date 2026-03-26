# Miner API Reference
Complete API reference for miner operations.

## Endpoints

### Register Miner

```
POST /v1/miners
```

**Request Body:**

```json
{
  "name": "my-miner",
  "gpu_type": "v100",
  "gpu_count": 1,
  "location": "us-east",
  "price_per_hour": 0.05,
  "max_concurrent": 4
}
```

**Response:**

```json
{
  "miner_id": "miner_xyz789",
  "api_key": "key_abc123",
  "status": "pending"
}
```

### Update Miner

```
PUT /v1/miners/{miner_id}
```

### Heartbeat

```
POST /v1/miners/{miner_id}/heartbeat
```

**Response:**

```json
{
  "status": "ok",
  "jobs_assigned": 0,
  "queue_length": 5
}
```

### List Available Jobs

```
GET /v1/miners/{miner_id}/jobs/available
```

**Response:**

```json
{
  "jobs": [
    {
      "job_id": "job_abc123",
      "model": "gpt2",
      "gpu_type": "v100",
      "gpu_count": 1,
      "estimated_time": 600,
      "price": 0.05
    }
  ]
}
```

### Accept Job

```
POST /v1/miners/{miner_id}/jobs/{job_id}/accept
```

### Complete Job

```
POST /v1/miners/{miner_id}/jobs/{job_id}/complete
```

**Request Body:**

```json
{
  "result_hash": "sha256:abc123...",
  "metrics": {
    "execution_time_seconds": 600,
    "gpu_time_seconds": 600
  }
}
```

### Get Miner Stats

```
GET /v1/miners/{miner_id}/stats
```

**Response:**

```json
{
  "total_jobs": 100,
  "success_rate": 0.98,
  "average_completion_time": 600,
  "earnings": 50.5,
  "earnings_per_gpu_hour": 0.05
}
```

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Invalid request |
| 401 | Unauthorized |
| 404 | Miner/job not found |
| 409 | Job already assigned |
| 422 | Validation error |

## Rate Limits

- 60 requests/minute
- 10 job operations/minute

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Job Management](./3_job-management.md) — Job management
- [Monitoring](./6_monitoring.md) - Monitor your miner
