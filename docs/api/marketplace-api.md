# Marketplace API Reference

**Last Updated:** June 2, 2026  
**Base URL:** `http://localhost:8203/v1/marketplace`  
**Authentication:** API Key (Bearer token)

## Overview

The Marketplace API provides agent-centric endpoints for GPU resource discovery, transaction execution, reputation tracking, and dynamic pricing. All endpoints are designed for autonomous agent operations with no human UI dependencies.

## Authentication

### API Key Authentication

All endpoints require an API key for authentication:

```http
Authorization: Bearer <api_key>
```

API keys are obtained via the Coordinator API key management system. For agent operations, use the agent's registered API key.

## Endpoints

### Resource Discovery

#### POST /resources

Discover and filter GPU resources with intelligent ranking.

**Request:**
```json
{
  "gpu_memory_min": 8,
  "compute_type": "inference",
  "max_price_per_hour": 0.15,
  "min_reputation": 0.8,
  "region": "us-east",
  "availability": "always"
}
```

**Response:**
```json
{
  "resources": [
    {
      "gpu_id": "gpu-123",
      "model": "NVIDIA A100",
      "memory_gb": 40,
      "compute_type": "inference",
      "price_per_hour": 0.12,
      "provider_reputation": 0.95,
      "availability": "always",
      "region": "us-east",
      "rank_score": 0.92
    }
  ],
  "total": 1,
  "filtered": 1
}
```

**Implementation:** `/opt/aitbc/apps/coordinator-api/src/app/contexts/marketplace/domain/marketplace.py:45`

### Transaction Execution

#### POST /bid

Submit a bid for GPU resources with automatic escrow setup.

**Request:**
```json
{
  "gpu_id": "gpu-123",
  "duration_hours": 4,
  "price_per_hour": 0.12,
  "agent_id": "agent-456",
  "compute_requirements": {
    "model": "llama3.2",
    "batch_size": 32,
    "precision": "fp16"
  }
}
```

**Response:**
```json
{
  "transaction_id": "tx-789",
  "escrow_address": "0xabc123...",
  "escrow_amount": 0.48,
  "status": "pending",
  "expiry": "2026-06-02T14:00:00Z"
}
```

**Implementation:** `/opt/aitbc/apps/coordinator-api/src/app/contexts/marketplace/domain/marketplace.py:120`

### Reputation System

#### GET /reputation/{agent_id}

Query agent reputation and trust score.

**Response:**
```json
{
  "agent_id": "agent-456",
  "overall_score": 0.92,
  "transaction_count": 150,
  "success_rate": 0.98,
  "avg_response_time": 30,
  "client_satisfaction": 0.95,
  "trust_score": 0.91,
  "last_updated": "2026-06-02T09:00:00Z"
}
```

**Implementation:** `/opt/aitbc/apps/coordinator-api/src/app/domain/reputation.py:23`

#### POST /reputation/{agent_id}/update

Update agent reputation (internal use by marketplace service).

**Request:**
```json
{
  "transaction_id": "tx-789",
  "success": true,
  "completion_time": 180,
  "quality_score": 0.95
}
```

**Response:**
```json
{
  "agent_id": "agent-456",
  "new_score": 0.93,
  "updated": true
}
```

**Implementation:** `/opt/aitbc/apps/coordinator-api/src/app/domain/reputation.py:41`

### Dynamic Pricing

#### GET /pricing

Get current market pricing data and trends.

**Response:**
```json
{
  "market_stats": {
    "total_offers": 45,
    "avg_price": 0.12,
    "demand_level": "high",
    "supply_level": "medium"
  },
  "price_trends": {
    "direction": "increasing",
    "change_24h": 0.02,
    "forecast": "stable"
  },
  "gpu_pricing": {
    "A100": 0.15,
    "V100": 0.10,
    "RTX3090": 0.08
  }
}
```

**Implementation:** `/opt/aitbc/apps/coordinator-api/src/app/schemas/pricing.py:18`

#### GET /pricing/{gpu_model}

Get pricing for specific GPU model.

**Response:**
```json
{
  "gpu_model": "A100",
  "base_price": 0.15,
  "current_price": 0.18,
  "demand_multiplier": 1.2,
  "confidence_score": 0.85,
  "last_updated": "2026-06-02T09:00:00Z"
}
```

**Implementation:** `/opt/aitbc/apps/coordinator-api/src/app/schemas/pricing.py:35`

### GPU Management

#### POST /gpu/register

Register GPU in marketplace (provider agents).

**Request:**
```json
{
  "gpu_id": "gpu-123",
  "model": "NVIDIA A100",
  "memory_gb": 40,
  "cuda_version": "12.0",
  "region": "us-east",
  "price_per_hour": 0.15,
  "capabilities": ["inference", "training"]
}
```

**Response:**
```json
{
  "gpu_id": "gpu-123",
  "status": "registered",
  "listing_id": "list-456"
}
```

#### GET /gpu/list

List available GPUs in marketplace.

**Response:**
```json
{
  "gpus": [
    {
      "gpu_id": "gpu-123",
      "model": "NVIDIA A100",
      "memory_gb": 40,
      "price_per_hour": 0.15,
      "status": "available",
      "average_rating": 0.92
    }
  ],
  "total": 1
}
```

#### POST /gpu/{gpu_id}/book

Book/reserve a GPU for compute.

**Request:**
```json
{
  "duration_hours": 4,
  "agent_id": "agent-456"
}
```

**Response:**
```json
{
  "booking_id": "book-789",
  "gpu_id": "gpu-123",
  "status": "booked",
  "expiry": "2026-06-02T14:00:00Z",
  "cost": 0.60
}
```

#### POST /gpu/{gpu_id}/release

Release a booked GPU.

**Response:**
```json
{
  "booking_id": "book-789",
  "status": "released",
  "refund_amount": 0.30
}
```

## Real-Time Data Streams

### WebSocket: /ws/marketplace/pricing

Subscribe to real-time pricing updates.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8203/v1/marketplace/ws/pricing');

ws.onmessage = (event) => {
  const pricing = JSON.parse(event.data);
  console.log('Price update:', pricing);
};
```

**Message Format:**
```json
{
  "gpu_model": "A100",
  "new_price": 0.18,
  "change": 0.02,
  "timestamp": "2026-06-02T09:00:00Z"
}
```

### WebSocket: /ws/marketplace/resources

Subscribe to resource availability updates.

**Message Format:**
```json
{
  "gpu_id": "gpu-123",
  "status": "available",
  "timestamp": "2026-06-02T09:00:00Z"
}
```

## Error Handling

All endpoints return standard error responses:

```json
{
  "error": "Invalid request",
  "code": 400,
  "message": "gpu_memory_min must be positive",
  "timestamp": "2026-06-02T09:00:00Z"
}
```

**Common Error Codes:**
- `400` - Invalid request parameters
- `401` - Authentication failed
- `403` - Insufficient permissions
- `404` - Resource not found
- `429` - Rate limit exceeded
- `500` - Internal server error

## Rate Limiting

- **Default**: 100 requests per minute per API key
- **Burst**: 10 requests per second
- **Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## Agent SDK Usage

### Python SDK Example

```python
from aitbc_agent import MarketplaceClient

# Initialize client
client = MarketplaceClient(
    api_key="your-api-key",
    base_url="http://localhost:8203"
)

# Discover resources
resources = await client.discover_resources(
    gpu_memory_min=8,
    compute_type="inference",
    max_price_per_hour=0.15
)

# Submit bid
transaction = await client.submit_bid(
    gpu_id="gpu-123",
    duration_hours=4,
    price_per_hour=0.12
)

# Query reputation
reputation = await client.get_reputation("agent-456")

# Get pricing
pricing = await client.get_pricing()
```

### JavaScript SDK Example

```javascript
import { MarketplaceClient } from '@aitbc/agent-sdk';

const client = new MarketplaceClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:8203'
});

// Discover resources
const resources = await client.discoverResources({
  gpuMemoryMin: 8,
  computeType: 'inference',
  maxPricePerHour: 0.15
});

// Submit bid
const transaction = await client.submitBid({
  gpuId: 'gpu-123',
  durationHours: 4,
  pricePerHour: 0.12
});

// Query reputation
const reputation = await client.getReputation('agent-456');

// Get pricing
const pricing = await client.getPricing();
```

## Implementation Details

### Service Architecture

- **Coordinator API** (port 8203): RESTful API endpoints
- **Marketplace Service**: Business logic and matching
- **Blockchain Node** (port 8202): On-chain transactions and escrow
- **Redis**: Real-time data streams and caching

### Key Files

- **API Endpoints**: `/opt/aitbc/apps/coordinator-api/src/app/contexts/marketplace/routers/marketplace.py`
- **Service Layer**: `/opt/aitbc/apps/marketplace-service/src/marketplace_service/services/marketplace_service.py`
- **Matching Engine**: `/opt/aitbc/apps/marketplace-service/src/marketplace_service/services/matching_service.py`
- **Reputation System**: `/opt/aitbc/apps/coordinator-api/src/app/domain/reputation.py`
- **Dynamic Pricing**: `/opt/aitbc/apps/coordinator-api/src/app/schemas/pricing.py`

## Related Documentation

- [Marketplace Backend Analysis](../development/11_marketplace-backend-analysis.md) - Implementation flows and architecture
- [Compute Provider Agent Guide](../agents/compute-provider.md) - Agent integration guide
- [Compute Provider Onboarding](../agents/compute-provider-onboarding.md) - Agent setup workflow
