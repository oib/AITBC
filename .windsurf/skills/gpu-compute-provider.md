# GPU Compute Provider Skill

## Description

This skill provides a complete workflow for GPU compute providers to register, manage GPU resources, and participate in the AITBC GPU marketplace. It covers the full lifecycle from miner registration to GPU offer submission, job polling, and earnings tracking.

## Prerequisites

- GPU service running on port 8101
- Valid miner_id and node_id
- GPU specifications (model, memory, capabilities)
- Marketplace pricing information

## Endpoints

### Working Endpoints

| Endpoint | Method | Purpose | Status |
|---------|--------|---------|--------|
| `/health` | GET | Health check | ✓ Working |
| `/gpu/status` | GET | GPU service status | ✓ Working |
| `/live` | GET | Liveness check | ✓ Working |
| `/v1/miners/register` | POST | Register miner | ✓ Working |
| `/v1/transactions` | POST | Submit GPU offer | ✓ Working |
| `/v1/transactions` | GET | Query transactions | ✓ Working |
| `/v1/miners/heartbeat` | POST | Send heartbeat | ✓ Working |
| `/v1/miners/{miner_id}/gpus` | GET | Get miner GPUs | ✓ Working |
| `/v1/miners/poll` | POST | Poll for jobs | ✓ Working |
| `/v1/miners/{miner_id}/earnings` | POST | Get earnings | ✓ Working |
| `/v1/miners/{miner_id}/capabilities` | PUT | Update capabilities | ✓ Working |
| `/v1/miners/{miner_id}` | DELETE | Deregister miner | ✓ Working |

### Non-Working Endpoints

| Endpoint | Issue |
|---------|-------|
| `/ready` | Database SQL expression error |
| `/v1/marketplace/edge-gpu/profiles` | 500 error (unimplemented) |
| `/v1/marketplace/edge-gpu/scan/{miner_id}` | 404 (unimplemented) |

## Workflow Steps

### 1. Register Miner

Register a new miner in the GPU marketplace.

```bash
curl -X POST http://localhost:8101/v1/miners/register \
  -H "Content-Type: application/json" \
  -d '{
    "miner_id": "compute_provider_001",
    "node_id": "node_aitbc_genesis",
    "location": "us-east"
  }'
```

**Response:**
```json
{
  "status": "ok",
  "miner_id": "compute_provider_001",
  "session_token": "token_0d1924d697bd47c3",
  "gpu_count": 0
}
```

### 2. Submit GPU Offers

Create GPU offers for the marketplace.

```bash
curl -X POST http://localhost:8101/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "gpu_marketplace",
    "action": "offer",
    "offer_id": "gpu_a100_001",
    "provider_node_id": "compute_provider_001",
    "price_per_gpu": 35.0,
    "specs": {
      "model": "NVIDIA A100",
      "memory_gb": 80,
      "region": "us-east",
      "capabilities": ["inference", "training", "fine-tuning"]
    },
    "status": "available"
  }'
```

**Response:**
```json
{
  "status": "success",
  "transaction_id": "gpu_a100_001"
}
```

### 3. Query Transactions

List all GPU marketplace transactions.

```bash
curl -X GET http://localhost:8101/v1/transactions
```

**Response:**
```json
[
  {
    "id": "gpu_a100_001",
    "action": "offer",
    "model": "NVIDIA A100",
    "memory_gb": 80,
    "price_per_hour": 35.0,
    "status": "available",
    "region": "us-east",
    "miner_id": "compute_provider_001",
    "created_at": "2026-05-14T16:19:58.656796"
  }
]
```

### 4. Get Miner GPUs

Retrieve GPUs registered by a specific miner.

```bash
curl -X GET http://localhost:8101/v1/miners/compute_provider_001/gpus
```

**Response:**
```json
[
  {
    "id": "gpu_a100_001",
    "model": "NVIDIA A100",
    "memory_gb": 80,
    "status": "online",
    "price_per_hour": 35.0,
    "region": "us-east",
    "created_at": "2026-05-14T16:19:58.656796"
  }
]
```

### 5. Send Heartbeat

Send a heartbeat to keep miner status online.

```bash
curl -X POST http://localhost:8101/v1/miners/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "miner_id": "compute_provider_001"
  }'
```

**Response:**
```json
{
  "status": "ok"
}
```

### 6. Poll for Jobs

Poll for available compute jobs.

```bash
curl -X POST http://localhost:8101/v1/miners/poll \
  -H "Content-Type: application/json" \
  -d '{
    "miner_id": "compute_provider_001",
    "max_wait_seconds": 5
  }'
```

**Response:**
```
null
```

*Note: Returns null when no jobs are available (placeholder implementation).*

### 7. Get Earnings

Retrieve miner earnings information.

```bash
curl -X POST http://localhost:8101/v1/miners/compute_provider_001/earnings
```

**Response:**
```json
{
  "miner_id": "compute_provider_001",
  "total_earnings": 0.0,
  "pending_earnings": 0.0,
  "currency": "AITBC"
}
```

### 8. Update Capabilities

Update miner capabilities.

```bash
curl -X PUT http://localhost:8101/v1/miners/compute_provider_001/capabilities \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": {
      "max_batch_size": 32,
      "supported_models": ["llama-7b", "gpt-3.5"]
    }
  }'
```

**Response:**
```json
{
  "status": "ok",
  "miner_id": "compute_provider_001",
  "capabilities": {
    "max_batch_size": 32,
    "supported_models": ["llama-7b", "gpt-3.5"]
  }
}
```

### 9. Deregister Miner

Deregister a miner from the marketplace.

```bash
curl -X DELETE http://localhost:8101/v1/miners/compute_provider_001
```

**Response:**
```json
{
  "status": "ok",
  "miner_id": "compute_provider_001",
  "message": "Miner deregistered"
}
```

## Complete Workflow Example

```bash
# 1. Register miner
MINER_ID="compute_provider_001"
curl -X POST http://localhost:8101/v1/miners/register \
  -H "Content-Type: application/json" \
  -d "{\"miner_id\": \"$MINER_ID\", \"node_id\": \"node_genesis\", \"location\": \"us-east\"}"

# 2. Submit GPU offers
curl -X POST http://localhost:8101/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "gpu_marketplace",
    "action": "offer",
    "offer_id": "gpu_a100_001",
    "provider_node_id": "compute_provider_001",
    "price_per_gpu": 35.0,
    "specs": {
      "model": "NVIDIA A100",
      "memory_gb": 80,
      "region": "us-east",
      "capabilities": ["inference", "training"]
    },
    "status": "available"
  }'

# 3. Query transactions
curl -X GET http://localhost:8101/v1/transactions

# 4. Get miner GPUs
curl -X GET http://localhost:8101/v1/miners/$MINER_ID/gpus

# 5. Send heartbeat
curl -X POST http://localhost:8101/v1/miners/heartbeat \
  -H "Content-Type: application/json" \
  -d "{\"miner_id\": \"$MINER_ID\"}"

# 6. Poll for jobs
curl -X POST http://localhost:8101/v1/miners/poll \
  -H "Content-Type: application/json" \
  -d "{\"miner_id\": \"$MINER_ID\", \"max_wait_seconds\": 5}"

# 7. Get earnings
curl -X POST http://localhost:8101/v1/miners/$MINER_ID/earnings

# 8. Update capabilities
curl -X PUT http://localhost:8101/v1/miners/$MINER_ID/capabilities \
  -H "Content-Type: application/json" \
  -d '{"capabilities": {"max_batch_size": 32, "supported_models": ["llama-7b"]}}'

# 9. Deregister miner (cleanup)
curl -X DELETE http://localhost:8101/v1/miners/$MINER_ID
```

## GPU Specifications

Common GPU models and specifications:

| Model | Memory | Typical Use Cases |
|-------|--------|-------------------|
| NVIDIA A100 | 80 GB | Training, inference, fine-tuning |
| NVIDIA H100 | 80 GB | High-performance training |
| NVIDIA RTX 4090 | 24 GB | Inference, light training |
| NVIDIA RTX 4060 Ti | 16 GB | Inference, edge computing |

## Pricing Guidelines

Recommended hourly pricing (AIT tokens):

| GPU Model | Price Range (AIT/hour) |
|-----------|----------------------|
| NVIDIA A100 | 25-40 |
| NVIDIA H100 | 35-50 |
| NVIDIA RTX 4090 | 15-25 |
| NVIDIA RTX 4060 Ti | 10-20 |

## Service Health Checks

```bash
# Health check
curl http://localhost:8101/health

# GPU status
curl http://localhost:8101/gpu/status

# Liveness check
curl http://localhost:8101/live
```

## Troubleshooting

- **/ready endpoint fails**: Database initialization issue with SQL expression. Service still operational for other endpoints.
- **Profiles endpoint 500 error**: Unimplemented feature. Not required for basic compute provider workflow.
- **Scan endpoint 404**: Unimplemented feature. Not required for basic compute provider workflow.
- **Poll returns null**: Expected behavior when no jobs are available (placeholder implementation).
- **Earnings show 0.0**: Expected for new miners with no completed jobs (placeholder implementation).

## Notes

- The `/ready` endpoint has a database SQL expression error but does not affect other functionality.
- Edge GPU profiles and scan endpoints are unimplemented and return errors.
- Job polling and earnings tracking are placeholder implementations.
- Use heartbeat regularly to keep miner status online.
- GPU offers persist in the database and can be queried via the transactions endpoint.
