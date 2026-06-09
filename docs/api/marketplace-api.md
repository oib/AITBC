# Marketplace API Reference

**Last Updated:** June 5, 2026
**Base URL:** `http://localhost:8102/v1/marketplace` (marketplace-service)
**API Gateway:** `http://localhost:8201/v1/marketplace`
**Authentication:** API Key (Bearer token)

> **Note:** The legacy coordinator-api (port 8203) is deprecated. Use port 8102 directly or 8201 via the API gateway.

> **⚠️ DEPRECATION NOTICE (v0.4.7)**: GPU-only marketplace with bids has been deprecated. The marketplace now focuses on hardware+software bundles with fixed pricing. The bid endpoint described below is no longer supported.

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

### Transaction Execution ~~(DEPRECATED)~~

> **⚠️ DEPRECATED (v0.4.7)**: The bid endpoint is no longer supported. Use offer booking instead.

~~**Request:**~~
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

~~**Response:**~~
```json
{
  "transaction_id": "tx-789",
  "escrow_address": "0xabc123...",
  "escrow_amount": 0.48,
  "status": "pending",
  "expiry": "2026-06-02T14:00:00Z"
}
```

~~**Implementation:**~~ `/opt/aitbc/apps/coordinator-api/src/app/contexts/marketplace/domain/marketplace.py:120`

**Current Implementation:** Use `POST /v1/marketplace/offers/{offer_id}/book` for booking hardware+software bundle offers with fixed pricing.

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

### Service Rating System

#### POST /offer/{service_id}/rate

Submit a rating for a software service (1-5 scale).

**Request:**
```json
{
  "rating": 4.5,
  "reviewer_id": "ait1abc123...",
  "comment": "Great service!"
}
```

**Response:**
```json
{
  "status": "success",
  "rating": {
    "id": "rating-uuid",
    "service_id": "ollama-llama3.2:3b",
    "rating": 4.5,
    "reviewer_id": "ait1abc123...",
    "comment": "Great service!",
    "created_at": "2026-06-05T10:40:43.469518",
    "source_node": "local"
  }
}
```

**Implementation:** `/opt/aitbc/apps/marketplace/src/marketplace_service/main.py:622`

#### GET /offer/{service_id}/ratings

Retrieve ratings for a service with pagination.

**Query Parameters:**
- `limit`: Number of ratings to return (default: 50)
- `offset`: Pagination offset (default: 0)

**Response:**
```json
{
  "service_id": "ollama-llama3.2:3b",
  "service_info": {
    "avg_rating": 4.2,
    "rating_count": 5
  },
  "ratings": [
    {
      "id": "rating-uuid",
      "service_id": "ollama-llama3.2:3b",
      "rating": 4.5,
      "reviewer_id": "ait1abc123...",
      "comment": "Great service!",
      "created_at": "2026-06-05T10:40:43.469518",
      "source_node": "local"
    }
  ],
  "count": 5,
  "limit": 50,
  "offset": 0
}
```

**Implementation:** `/opt/aitbc/apps/marketplace/src/marketplace_service/main.py:676`

#### GET /ratings/unsynced

Fetch ratings that haven't been synced to remote nodes.

**Query Parameters:**
- `limit`: Number of ratings to return (default: 100)

**Response:**
```json
{
  "ratings": [
    {
      "id": "rating-uuid",
      "service_id": "ollama-llama3.2:3b",
      "rating": 4.5,
      "reviewer_id": "ait1abc123...",
      "comment": "Great service!",
      "created_at": "2026-06-05T10:40:43.469518",
      "source_node": "local"
    }
  ],
  "count": 3
}
```

**Implementation:** `/opt/aitbc/apps/marketplace/src/marketplace_service/main.py:718`

#### POST /ratings/sync

Sync ratings from a remote node with conflict resolution.

**Request:**
```json
[
  {
    "id": "rating-uuid",
    "service_id": "ollama-llama3.2:3b",
    "rating": 4.5,
    "reviewer_id": "ait1abc123...",
    "comment": "Great service!",
    "created_at": "2026-06-05T10:40:43.469518",
    "source_node": "hub"
  }
]
```

**Response:**
```json
{
  "status": "success",
  "synced": 1,
  "updated": 0,
  "skipped": 0
}
```

**Implementation:** `/opt/aitbc/apps/marketplace/src/marketplace_service/main.py:728`

#### POST /ratings/mark-synced

Mark ratings as synced after successful propagation.

**Request:**
```json
["rating-uuid-1", "rating-uuid-2"]
```

**Response:**
```json
{
  "status": "success",
  "marked_synced": 2
}
```

**Implementation:** `/opt/aitbc/apps/marketplace/src/marketplace_service/main.py:745`

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

## Escrow Integration

When `POST /v1/marketplace/offers/{offer_id}/book` is called, the marketplace-service automatically creates a blockchain escrow to lock buyer funds. The escrow lifecycle is managed via the blockchain node RPC.

### Booking Response (with escrow)

```json
{
  "bid_id": "abc123",
  "offer_id": "offer-789",
  "status": "pending",
  "message": "Bid created successfully",
  "escrow_contract_id": "f3adfe6920c69422"
}
```

### Managing Escrow via CLI

```bash
# Check escrow state
aitbc market escrow status <bid_id>

# Release to provider (after job completes)
aitbc market escrow release <bid_id>

# Refund to buyer
aitbc market escrow refund <bid_id>
```

See the full [Escrow API Reference](./escrow-api.md) for direct RPC access.

## Service Architecture

| Service | Port | Role |
|---|---|---|
| `aitbc-marketplace` | 8102 | Marketplace offers/bids — **production** |
| `aitbc-blockchain-rpc` | 8202 | Blockchain transactions + escrow RPC |
| `aitbc-api-gateway` | 8201 | Public gateway (`/v1/marketplace`, `/v1/escrow`) |
| `aitbc-coordinator-api` | 8203 | **Legacy** — do not add features |

## Related Documentation

- [Escrow API Reference](./escrow-api.md) - Blockchain escrow endpoints
- [Blockchain Node API](./blockchain/README.md) - Blockchain RPC reference
- [CLI Marketplace Tools](../apps/marketplace/CLI_TOOLS.md) - CLI command reference
- [Compute Provider Agent Guide](../agents/compute-provider.md) - Agent integration guide
