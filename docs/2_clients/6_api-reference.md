# Client API Reference

REST API endpoints for client operations.

## Endpoints

### Submit Job

```
POST /v1/jobs
```

**Request Body:**

```json
{
  "model": "gpt2",
  "input": "string or file_id",
  "output_config": {
    "destination": "local or s3://bucket/path",
    "format": "json"
  },
  "requirements": {
    "gpu_type": "v100",
    "gpu_count": 1,
    "min_vram_gb": 16
  },
  "priority": "normal",
  "timeout_seconds": 3600
}
```

**Response:**

```json
{
  "job_id": "job_abc123",
  "estimated_cost": 0.05,
  "estimated_time_seconds": 600
}
```

### Get Job Status

```
GET /v1/jobs/{job_id}
```

**Response:**

```json
{
  "job_id": "job_abc123",
  "status": "running",
  "progress": 45,
  "miner_id": "miner_xyz789",
  "created_at": "2026-02-13T10:00:00Z",
  "started_at": "2026-02-13T10:01:00Z",
  "completed_at": null,
  "result": null
}
```

### List Jobs

```
GET /v1/jobs?status=running&limit=10
```

**Response:**

```json
{
  "jobs": [
    {
      "job_id": "job_abc123",
      "status": "running",
      "model": "gpt2"
    }
  ],
  "total": 1,
  "has_more": false
}
```

### Cancel Job

```
DELETE /v1/jobs/{job_id}
```

### Download Results

```
GET /v1/jobs/{job_id}/download
```

### Get Job History

```
GET /v1/jobs/history?from=2026-01-01&to=2026-01-31
```

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Invalid request |
| 401 | Unauthorized |
| 404 | Job not found |
| 422 | Validation error |
| 429 | Rate limited |
| 500 | Server error |

## Rate Limits

- 60 requests/minute
- 1000 requests/hour

## Next

- [1_quick-start.md](./1_quick-start.md) — Get started quickly
- [2_job-submission.md](./2_job-submission.md) — CLI-based job submission
- [CLI Guide](../0_getting_started/3_cli.md) — Full CLI reference
