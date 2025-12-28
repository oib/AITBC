---
title: API Endpoints
description: Complete list of Coordinator API endpoints
---

# API Endpoints

## Jobs

### Create Job
```http
POST /v1/jobs
```

Create a new AI job.

**Request Body:**
```json
{
  "name": "image-classification",
  "type": "ai-inference",
  "model": {
    "type": "python",
    "entrypoint": "model.py",
    "requirements": ["numpy", "torch"]
  },
  "input": {
    "type": "image",
    "format": "jpeg"
  },
  "output": {
    "type": "json"
  },
  "resources": {
    "cpu": "1000m",
    "memory": "2Gi",
    "gpu": "1"
  },
  "pricing": {
    "max_cost": "0.10"
  }
}
```

**Response:**
```json
{
  "job_id": "job_1234567890",
  "status": "submitted",
  "created_at": "2024-01-01T12:00:00Z",
  "estimated_completion": "2024-01-01T12:05:00Z"
}
```

### Get Job Status
```http
GET /v1/jobs/{job_id}
```

Retrieve the current status of a job.

**Response:**
```json
{
  "job_id": "job_1234567890",
  "status": "running",
  "progress": 75,
  "created_at": "2024-01-01T12:00:00Z",
  "started_at": "2024-01-01T12:01:00Z",
  "estimated_completion": "2024-01-01T12:05:00Z",
  "miner_id": "miner_1234567890"
}
```

### List Jobs
```http
GET /v1/jobs
```

List all jobs with optional filtering.

**Query Parameters:**
- `status` (string): Filter by status (submitted, running, completed, failed)
- `type` (string): Filter by job type
- `limit` (integer): Maximum number of jobs to return (default: 50)
- `offset` (integer): Number of jobs to skip (default: 0)

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "job_1234567890",
      "status": "completed",
      "type": "ai-inference",
      "created_at": "2024-01-01T12:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### Cancel Job
```http
DELETE /v1/jobs/{job_id}
```

Cancel a running or submitted job.

**Response:**
```json
{
  "job_id": "job_1234567890",
  "status": "cancelled",
  "cancelled_at": "2024-01-01T12:03:00Z"
}
```

### Get Job Results
```http
GET /v1/jobs/{job_id}/results
```

Retrieve the results of a completed job.

**Response:**
```json
{
  "job_id": "job_1234567890",
  "status": "completed",
  "results": {
    "prediction": "cat",
    "confidence": 0.95,
    "processing_time": 1.23
  },
  "completed_at": "2024-01-01T12:04:00Z"
}
```

## Marketplace

### Create Offer
```http
POST /v1/marketplace/offers
```

Create a new marketplace offer for job execution.

**Request Body:**
```json
{
  "job_type": "image-classification",
  "price": "0.001",
  "max_jobs": 10,
  "requirements": {
    "min_gpu_memory": "4Gi",
    "min_cpu": "2000m"
  },
  "duration": 3600
}
```

**Response:**
```json
{
  "offer_id": "offer_1234567890",
  "miner_id": "miner_1234567890",
  "status": "active",
  "created_at": "2024-01-01T12:00:00Z"
}
```

### List Offers
```http
GET /v1/marketplace/offers
```

List all active marketplace offers.

**Query Parameters:**
- `job_type` (string): Filter by job type
- `max_price` (string): Maximum price filter
- `limit` (integer): Maximum number of offers (default: 50)

**Response:**
```json
{
  "offers": [
    {
      "offer_id": "offer_1234567890",
      "miner_id": "miner_1234567890",
      "job_type": "image-classification",
      "price": "0.001",
      "reputation": 4.8
    }
  ]
}
```

### Accept Offer
```http
POST /v1/marketplace/offers/{offer_id}/accept
```

Accept a marketplace offer for job execution.

**Request Body:**
```json
{
  "job_id": "job_1234567890",
  "bid_price": "0.001"
}
```

**Response:**
```json
{
  "transaction_id": "tx_1234567890",
  "status": "pending",
  "created_at": "2024-01-01T12:00:00Z"
}
```

## Receipts

### Get Receipt
```http
GET /v1/receipts/{job_id}
```

Retrieve the receipt for a completed job.

**Response:**
```json
{
  "receipt_id": "receipt_1234567890",
  "job_id": "job_1234567890",
  "miner_id": "miner_1234567890",
  "signature": {
    "sig": "base64_signature",
    "public_key": "base64_public_key"
  },
  "attestations": [
    {
      "type": "completion",
      "timestamp": "2024-01-01T12:04:00Z",
      "signature": "base64_attestation"
    }
  ],
  "created_at": "2024-01-01T12:04:00Z"
}
```

### Verify Receipt
```http
POST /v1/receipts/verify
```

Verify the authenticity of a receipt.

**Request Body:**
```json
{
  "receipt": {
    "receipt_id": "receipt_1234567890",
    "signature": {
      "sig": "base64_signature",
      "public_key": "base64_public_key"
    }
  }
}
```

**Response:**
```json
{
  "valid": true,
  "miner_signature_valid": true,
  "coordinator_attestations": 2,
  "verified_at": "2024-01-01T12:05:00Z"
}
```

## Analytics

### Get Marketplace Stats
```http
GET /v1/marketplace/stats
```

Retrieve marketplace statistics.

**Response:**
```json
{
  "total_jobs": 10000,
  "active_jobs": 150,
  "completed_jobs": 9800,
  "failed_jobs": 50,
  "average_completion_time": 120.5,
  "total_volume": "1500.50",
  "active_miners": 500
}
```

### Get Miner Stats
```http
GET /v1/miners/{miner_id}/stats
```

Retrieve statistics for a specific miner.

**Response:**
```json
{
  "miner_id": "miner_1234567890",
  "reputation": 4.8,
  "total_jobs": 500,
  "success_rate": 0.98,
  "average_completion_time": 115.2,
  "total_earned": "125.50",
  "active_since": "2024-01-01T00:00:00Z"
}
```

## Health

### Health Check
```http
GET /v1/health
```

Production base URL is `https://aitbc.bubuit.net/api`, so the full health URL is:
```http
GET /api/v1/health
```

Check the health status of the coordinator service.

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "timestamp": "2024-01-01T12:00:00Z",
  "services": {
    "database": "healthy",
    "blockchain": "healthy",
    "marketplace": "healthy"
  }
}
```

## WebSocket API

### Real-time Updates
```
WSS /ws
```

Connect to receive real-time updates about jobs and marketplace events.

**Message Types:**
- `job_update`: Job status changes
- `marketplace_update`: New offers or transactions
- `receipt_created`: New receipts generated

**Example Message:**
```json
{
  "type": "job_update",
  "data": {
    "job_id": "job_1234567890",
    "status": "completed",
    "timestamp": "2024-01-01T12:04:00Z"
  }
}
```

## Error Codes

| Code | Description | HTTP Status |
|------|-------------|-------------|
| `INVALID_JOB_TYPE` | Unsupported job type | 400 |
| `INSUFFICIENT_BALANCE` | Not enough funds in wallet | 402 |
| `JOB_NOT_FOUND` | Job does not exist | 404 |
| `JOB_ALREADY_COMPLETED` | Cannot modify completed job | 409 |
| `OFFER_NOT_AVAILABLE` | Offer is no longer available | 410 |
| `RATE_LIMIT_EXCEEDED` | Too many requests | 429 |
| `INTERNAL_ERROR` | Server error | 500 |

## SDK Examples

### Python
```python
from aitbc import AITBCClient

client = AITBCClient(api_key="your_key")

# Create a job
job = client.jobs.create({
    "name": "my-job",
    "type": "ai-inference",
    ...
})

# Get results
results = client.jobs.get_results(job["job_id"])
```

### JavaScript
```javascript
import { AITBCClient } from '@aitbc/client';

const client = new AITBCClient({ apiKey: 'your_key' });

// Create a job
const job = await client.jobs.create({
  name: 'my-job',
  type: 'ai-inference',
  ...
});

// Get results
const results = await client.jobs.getResults(job.jobId);
```

## Services

### Whisper Transcription
```http
POST /v1/services/whisper/transcribe
```

Transcribe audio file using Whisper.

**Request Body:**
```json
{
  "audio_url": "https://example.com/audio.mp3",
  "model": "base",
  "language": "en",
  "task": "transcribe"
}
```

### Stable Diffusion Generation
```http
POST /v1/services/stable-diffusion/generate
```

Generate images from text prompts.

**Request Body:**
```json
{
  "prompt": "A beautiful sunset over mountains",
  "model": "stable-diffusion-1.5",
  "size": "1024x1024",
  "num_images": 1,
  "steps": 20
}
```

### LLM Inference
```http
POST /v1/services/llm/inference
```

Run inference on language models.

**Request Body:**
```json
{
  "model": "llama-7b",
  "prompt": "Explain quantum computing",
  "max_tokens": 256,
  "temperature": 0.7
}
```

### Video Transcoding
```http
POST /v1/services/ffmpeg/transcode
```

Transcode video files.

**Request Body:**
```json
{
  "input_url": "https://example.com/video.mp4",
  "output_format": "mp4",
  "codec": "h264",
  "resolution": "1920x1080"
}
```

### 3D Rendering
```http
POST /v1/services/blender/render
```

Render 3D scenes with Blender.

**Request Body:**
```json
{
  "blend_file_url": "https://example.com/scene.blend",
  "engine": "cycles",
  "resolution_x": 1920,
  "resolution_y": 1080,
  "samples": 128
}
```

## Service Registry

### List All Services
```http
GET /v1/registry/services
```

List all available GPU services with optional filtering.

**Query Parameters:**
- `category` (optional): Filter by service category
- `search` (optional): Search by name, description, or tags

### Get Service Definition
```http
GET /v1/registry/services/{service_id}
```

Get detailed definition for a specific service.

### Get Service Schema
```http
GET /v1/registry/services/{service_id}/schema
```

Get JSON schema for service input parameters.

### Get Service Requirements
```http
GET /v1/registry/services/{service_id}/requirements
```

Get hardware requirements for a service.

### Validate Service Request
```http
POST /v1/registry/services/validate
```

Validate a service request against the service schema.

**Request Body:**
```json
{
  "service_id": "llm_inference",
  "request_data": {
    "model": "llama-7b",
    "prompt": "Hello world",
    "max_tokens": 256
  }
}
```

**Response:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```
