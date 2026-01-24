# Integrating with Coordinator API

This tutorial shows how to integrate your application with the AITBC Coordinator API.

## API Overview

The Coordinator API is the central hub for:
- Job submission and management
- Miner registration and discovery
- Receipt generation and verification
- Network statistics

**Base URL**: `https://aitbc.bubuit.net/api`

## Authentication

### Public Endpoints
Some endpoints are public and don't require authentication:
- `GET /health` - Health check
- `GET /v1/stats` - Network statistics

### Authenticated Endpoints
For job submission and management, use an API key:

```bash
curl -H "X-Api-Key: your-api-key" https://aitbc.bubuit.net/api/v1/jobs
```

## Core Endpoints

### Jobs

#### Submit a Job

```bash
POST /v1/jobs
Content-Type: application/json

{
  "prompt": "Explain quantum computing",
  "model": "llama3.2",
  "params": {
    "max_tokens": 256,
    "temperature": 0.7
  }
}
```

**Response:**
```json
{
  "job_id": "job-abc123",
  "status": "pending",
  "created_at": "2026-01-24T15:00:00Z"
}
```

#### Get Job Status

```bash
GET /v1/jobs/{job_id}
```

**Response:**
```json
{
  "job_id": "job-abc123",
  "status": "completed",
  "result": "Quantum computing is...",
  "miner_id": "miner-xyz",
  "started_at": "2026-01-24T15:00:01Z",
  "completed_at": "2026-01-24T15:00:05Z"
}
```

#### List Jobs

```bash
GET /v1/jobs?status=completed&limit=10
```

#### Cancel a Job

```bash
POST /v1/jobs/{job_id}/cancel
```

### Miners

#### Register Miner

```bash
POST /v1/miners/register
Content-Type: application/json

{
  "miner_id": "my-miner-001",
  "capabilities": ["llama3.2", "codellama"],
  "gpu_info": {
    "name": "NVIDIA RTX 4090",
    "memory": "24GB"
  }
}
```

#### Get Available Jobs (for miners)

```bash
GET /v1/jobs/available?miner_id=my-miner-001
```

#### Claim a Job

```bash
POST /v1/jobs/{job_id}/claim
Content-Type: application/json

{
  "miner_id": "my-miner-001"
}
```

#### Complete a Job

```bash
POST /v1/jobs/{job_id}/complete
Content-Type: application/json

{
  "miner_id": "my-miner-001",
  "result": "The generated output...",
  "completed_at": "2026-01-24T15:00:05Z"
}
```

### Receipts

#### Get Receipt

```bash
GET /v1/receipts/{receipt_id}
```

#### List Receipts

```bash
GET /v1/receipts?client=ait1client...&limit=20
```

### Explorer Endpoints

```bash
GET /explorer/blocks          # Recent blocks
GET /explorer/transactions    # Recent transactions
GET /explorer/receipts        # Recent receipts
GET /explorer/stats           # Network statistics
```

## Python Integration

### Using httpx

```python
import httpx

class CoordinatorClient:
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url
        self.headers = {}
        if api_key:
            self.headers["X-Api-Key"] = api_key
        self.client = httpx.Client(headers=self.headers, timeout=30.0)
    
    def submit_job(self, prompt: str, model: str = "llama3.2", **params) -> dict:
        response = self.client.post(
            f"{self.base_url}/v1/jobs",
            json={"prompt": prompt, "model": model, "params": params}
        )
        response.raise_for_status()
        return response.json()
    
    def get_job(self, job_id: str) -> dict:
        response = self.client.get(f"{self.base_url}/v1/jobs/{job_id}")
        response.raise_for_status()
        return response.json()
    
    def wait_for_job(self, job_id: str, timeout: int = 60) -> dict:
        import time
        start = time.time()
        while time.time() - start < timeout:
            job = self.get_job(job_id)
            if job["status"] in ["completed", "failed", "cancelled"]:
                return job
            time.sleep(2)
        raise TimeoutError(f"Job {job_id} did not complete in {timeout}s")

# Usage
client = CoordinatorClient("https://aitbc.bubuit.net/api")
job = client.submit_job("Hello, world!")
result = client.wait_for_job(job["job_id"])
print(result["result"])
```

### Async Version

```python
import httpx
import asyncio

class AsyncCoordinatorClient:
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url
        headers = {"X-Api-Key": api_key} if api_key else {}
        self.client = httpx.AsyncClient(headers=headers, timeout=30.0)
    
    async def submit_job(self, prompt: str, model: str = "llama3.2") -> dict:
        response = await self.client.post(
            f"{self.base_url}/v1/jobs",
            json={"prompt": prompt, "model": model}
        )
        response.raise_for_status()
        return response.json()
    
    async def wait_for_job(self, job_id: str, timeout: int = 60) -> dict:
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            response = await self.client.get(f"{self.base_url}/v1/jobs/{job_id}")
            job = response.json()
            if job["status"] in ["completed", "failed"]:
                return job
            await asyncio.sleep(2)
        raise TimeoutError()

# Usage
async def main():
    client = AsyncCoordinatorClient("https://aitbc.bubuit.net/api")
    job = await client.submit_job("Explain AI")
    result = await client.wait_for_job(job["job_id"])
    print(result["result"])

asyncio.run(main())
```

## JavaScript Integration

```javascript
class CoordinatorClient {
  constructor(baseUrl, apiKey = null) {
    this.baseUrl = baseUrl;
    this.headers = { 'Content-Type': 'application/json' };
    if (apiKey) this.headers['X-Api-Key'] = apiKey;
  }

  async submitJob(prompt, model = 'llama3.2', params = {}) {
    const response = await fetch(`${this.baseUrl}/v1/jobs`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ prompt, model, params })
    });
    return response.json();
  }

  async getJob(jobId) {
    const response = await fetch(`${this.baseUrl}/v1/jobs/${jobId}`, {
      headers: this.headers
    });
    return response.json();
  }

  async waitForJob(jobId, timeout = 60000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const job = await this.getJob(jobId);
      if (['completed', 'failed', 'cancelled'].includes(job.status)) {
        return job;
      }
      await new Promise(r => setTimeout(r, 2000));
    }
    throw new Error('Timeout');
  }
}

// Usage
const client = new CoordinatorClient('https://aitbc.bubuit.net/api');
const job = await client.submitJob('Hello!');
const result = await client.waitForJob(job.job_id);
console.log(result.result);
```

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (invalid parameters) |
| 401 | Unauthorized (invalid API key) |
| 404 | Not Found |
| 429 | Rate Limited |
| 500 | Server Error |

### Error Response Format

```json
{
  "detail": "Job not found",
  "error_code": "JOB_NOT_FOUND"
}
```

### Retry Logic

```python
import time
from httpx import HTTPStatusError

def with_retry(func, max_retries=3, backoff=2):
    for attempt in range(max_retries):
        try:
            return func()
        except HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", backoff))
                time.sleep(retry_after)
            elif e.response.status_code >= 500:
                time.sleep(backoff * (attempt + 1))
            else:
                raise
    raise Exception("Max retries exceeded")
```

## Webhooks (Coming Soon)

Register a webhook to receive job completion notifications:

```bash
POST /v1/webhooks
Content-Type: application/json

{
  "url": "https://your-app.com/webhook",
  "events": ["job.completed", "job.failed"]
}
```

## Next Steps

- [Building a Custom Miner](building-custom-miner.md)
- [SDK Examples](sdk-examples.md)
- [API Reference](../../reference/components/coordinator_api.md)
