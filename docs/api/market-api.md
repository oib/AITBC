# Market API Reference

**Last Updated:** June 5, 2026
**Base URL:** `http://localhost:8102/v1/market` (market-service)
**API Gateway:** `http://localhost:8201/v1/market`
**Authentication:** Mixed — see below

> **Note:** The coordinator-api (port 8203) is **not** deprecated — it is the live job-submission and orchestration API (`POST /v1/jobs`, miner registration, receipts). This document covers the standalone market-service on port 8102, plus the GPU-market and reputation routes that live on the coordinator-api — those are flagged with their own base URL where they appear.
>
> **⚠️ DEPRECATION NOTICE (v0.4.7)**: GPU-only market with bids has been deprecated. The market now focuses on hardware+software bundles with fixed pricing. The bid endpoint described below is no longer supported.

## Overview

The market-service (`aitbc-market`, port 8102) manages hardware+software bundle offers, matching, market jobs, ratings, plugins, edge-node advertisements, and governance-applied parameter changes. GPU rental primitives (register/list/book/release/quote/purchase) live on the coordinator-api (port 8203) under `/v1/market/gpu/*`.

## Authentication

### Mixed authentication model

The market-service does **not** require an API key on every endpoint. Only the admin route `POST /v1/market/parameters/apply` (governance-approved parameter changes) is key-gated, via `APIKeyAuthenticator` from the shared `aitbc/auth` library:

```http
X-Api-Key: <market admin api key>
```

Note the header is `X-Api-Key`, **not** `Authorization: Bearer` — Bearer JWTs are the coordinator-api's customer auth scheme and are not used here. When `settings.auth_enabled` is false the dependency is a no-op; when the service's `api_key` setting is unset the gated route returns `501 API key not configured`. All other endpoints on this service are currently unauthenticated.

The market-service calls the blockchain node's escrow RPC with its own `BLOCKCHAIN_RPC_API_KEY` (`X-API-Key` header) — that key is service-to-service and is not a customer credential.

The coordinator-api GPU routes use the coordinator's own auth: miner routes need a miner JWT or `X-Api-Key`/`X-Miner-ID` (`MinerDep`); booking routes accept any authenticated user (`AuthDep`).

## Endpoints

### Resource Discovery

#### GET /v1/market/offers  *(market-service :8102)*

List market offers. Optional query filters: `status`, `region`, `gpu_model`, `chain_id`. Returns a JSON list of offers.

#### POST /v1/market/match  *(market-service :8102)*

Match a compute request to the best available GPU offer (price-time priority; reserves the matched offer via the offer FSM).

**Request:**

```json
{
  "requirements": {"gpu": "v100", "min_vram_gb": 16},
  "max_price": 0.15,
  "preferred_region": "us-east",
  "chain_id": "ait-mainnet"
}
```

**Response:**

```json
{
  "status": "success",
  "match": {"offer_id": "...", "...": "..."}
}
```

#### GET /v1/market/gpu/list  *(coordinator-api :8203)*

List registered GPUs. Optional query filters: `available` (bool), `price_max`, `region`, `model`, `limit` (1–500, default 100). Returns a list of GPU records (`id`, `miner_id`, `model`, `memory_gb`, `cuda_version`, `region`, `price_per_hour`, `status`, `capabilities`, `created_at`, `average_rating`, `total_reviews`).

> `POST /v1/market/resources` does not exist on either service — use the endpoints above.

### Offers and booking  *(market-service :8102)*

| Method | Path | Description |
|---|---|---|
| POST | `/v1/market/offers` | Create an offer (`provider` defaults from `wallet`/`metadata`) |
| GET | `/v1/market/offers/{offer_id}` | Get one offer |
| GET | `/v1/market/offers/{offer_id}/history` | Offer history |
| POST | `/v1/market/offers/{offer_id}/book` | Book an available offer; creates escrow in background when the booking carries `wallet`/`buyer`, `provider`, and `amount`/`price` |
| POST | `/v1/market/offers/{offer_id}/cancel` | Cancel an offer (`?reason=` optional) |
| POST | `/v1/market/bids/{bid_id}/complete` | Complete a bid once on-chain payment confirms (body needs `tx_hash`) |

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

**Current implementation:** `POST /v1/market/offers/{offer_id}/book` on the market-service (fixed-price bundle booking), or the GPU rental flow on the Coordinator API (port 8203) — `POST /v1/market/gpu/quote` → `POST /v1/market/gpu/purchase`. A `POST /v1/market/gpu/bid` stub still exists on the Coordinator API but only records a bid in-memory and is deprecated.

### Reputation

Reputation is served by the **coordinator-api (port 8203)**, mounted at `/v1/reputation` — not by the market-service. `GET /v1/market/reputation/{agent_id}` and `POST /v1/market/reputation/{agent_id}/update` do not exist.

Real coordinator-api reputation routes include:

| Method | Path | Description |
|---|---|---|
| GET | `/v1/reputation/profile/{agent_id}` | Full reputation profile (`trust_score`, `reputation_level`, `performance_rating`, `reliability_score`, `community_rating`, `total_earnings`, `transaction_count`, `success_rate`, `jobs_completed`, `jobs_failed`, `average_response_time`, `dispute_count`, `certifications`, `specialization_tags`, `geographic_region`, `last_activity`, `recent_events`) |
| POST | `/v1/reputation/profile/{agent_id}` | Create/update a reputation profile |
| GET | `/v1/reputation/trust-score/{agent_id}` | Trust score only |
| POST | `/v1/reputation/feedback/{agent_id}` | Submit feedback for an agent |
| GET | `/v1/reputation/feedback/{agent_id}` | List feedback for an agent |
| POST | `/v1/reputation/job-completion` | Record a job completion (internal service use — the miner router calls this) |
| GET | `/v1/reputation/leaderboard` | Reputation leaderboard |
| GET | `/v1/reputation/metrics` | Aggregate reputation metrics |
| GET | `/v1/reputation/events/{agent_id}` | Reputation event history |
| PUT | `/v1/reputation/profile/{agent_id}/specialization` | Update specialization tags |
| PUT | `/v1/reputation/profile/{agent_id}/region` | Update geographic region |

### Service Rating System  *(market-service :8102)*

#### POST /v1/market/offer/{service_id}/rate

Submit a rating for a software service (1–5 scale). 404 when the service does not exist.

**Request:**

```json
{
  "rating": 4.5,
  "reviewer_id": "0x...",
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
    "reviewer_id": "0x...",
    "comment": "Great service!",
    "created_at": "2026-06-05T10:40:43.469518"
  }
}
```

#### GET /v1/market/offer/{service_id}/ratings

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
      "reviewer_id": "0x...",
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

#### GET /v1/market/ratings/unsynced

Fetch ratings that haven't been synced to remote nodes.

**Query Parameters:**

- `limit`: Number of ratings to return (default: 100)

#### POST /v1/market/ratings/sync

Sync ratings from a remote node with conflict resolution. Body is a list of rating objects; returns `{"status": "success", "synced": N, "updated": N, "skipped": N}`.

#### POST /v1/market/ratings/mark-synced

Mark ratings as synced after successful propagation. Body is a list of rating ID strings; returns `{"status": "success", "marked_synced": N}`.

**Implementation:** `/opt/aitbc/apps/market/src/market_service/main.py` (rating routes) and `services/market_service.py` (rating storage/sync).

### Dynamic Pricing

#### POST /v1/market/dynamic-pricing  *(market-service :8102)*

Calculate a suggested price for an offer from supply/demand. Required query parameters: `offer_id`, `current_demand` (int), `current_supply` (int).

**Response:**

```json
{
  "offer_id": "offer-123",
  "base_price": "0.15",
  "suggested_price": "0.18",
  "price_multiplier": 1.2,
  "supply_demand_ratio": 1.8,
  "current_demand": 9,
  "current_supply": 5,
  "reason": "dynamic_pricing_calculation"
}
```

#### GET /v1/market/analytics  *(market-service :8102)*

Market analytics; `?period_type=` (default `daily`). `GET /v1/market/performance?period=daily` returns the performance-metric view of the same data, and `GET /v1/market` returns the offer overview (counts, average price, regions, service types).

#### GET /v1/market/pricing/{model}  *(coordinator-api :8203)*

Static + dynamic pricing for a GPU model across registered GPUs (min/max/average static price, recommended dynamic price, per-GPU pricing, market analysis). 404 when no registered GPU matches the model.

> `GET /v1/market/pricing` (all-models market overview) does not exist on either service.

### GPU Management  *(coordinator-api :8203 only)*

These routes live on the coordinator-api under `/v1/market/gpu/*`. None of them exist on the market-service.

#### POST /v1/market/gpu/register

Register a GPU (miner auth — `MinerDep`). The authenticated miner is the canonical owner.

**Request:**

```json
{
  "gpu": {
    "name": "NVIDIA A100",
    "model_id": "a100-40g",
    "memory_gb": 40,
    "compute_capability": "12.0",
    "region": "us-east",
    "price_per_hour": "0.15",
    "resource_id": "res-1",
    "protected": false
  }
}
```

**Response:**

```json
{
  "gpu_id": "gpu_ab12cd34",
  "status": "registered",
  "message": "GPU NVIDIA A100 registered successfully",
  "price_per_hour": "0.15"
}
```

#### GET /v1/market/gpu/{gpu_id}

GPU details; includes `current_booking` when the GPU is booked. 404 when unknown.

#### POST /v1/market/gpu/{gpu_id}/book

Book an available GPU with dynamic pricing (authenticated — `AuthDep`). `201 Created`.

**Request:** `{"duration_hours": 4, "job_id": "job-abc"}` (`job_id` optional; `duration_hours` must be 0 < x ≤ 8760)

**Response:**

```json
{
  "booking_id": "book-789",
  "gpu_id": "gpu_ab12cd34",
  "status": "booked",
  "total_cost": "0.60",
  "base_price": "0.15",
  "dynamic_price": "0.15",
  "price_per_hour": "0.15",
  "start_time": "2026-06-02T10:00:00Z",
  "end_time": "2026-06-02T14:00:00Z",
  "pricing_factors": {},
  "confidence_score": 0.8
}
```

#### POST /v1/market/gpu/{gpu_id}/release

Release a booked GPU (authenticated). Returns `{"status": "released", "gpu_id": ..., "refund": ...}` — or `{"status": "already_available"}` when not booked.

Other coordinator-api GPU routes: `POST /v1/market/gpu/quote` (unsigned energy quote + bound job), `POST /v1/market/gpu/purchase`, `POST /v1/market/gpu/sell`, `POST /v1/market/gpu/{gpu_id}/confirm` (client ACK), `DELETE /v1/market/gpu/{gpu_id}`, `GET|POST /v1/market/gpu/{gpu_id}/reviews`, `GET /v1/market/orders`, `POST /v1/tasks/ollama`, `POST /v1/payments/send`, `POST /v1/market/native-energy/profile`, `POST /v1/market/native-energy/rate`, and the deprecated `POST /v1/market/gpu/bid` stub.

## Real-Time Data Streams

**The market-service exposes no WebSocket endpoints**, and neither does the coordinator-api. Poll `GET /v1/market/status`, the offer endpoints, and `GET /v1/jobs/{job_id}` (coordinator) for updates. The only WebSocket endpoints in the platform are the blockchain node's `WS /rpc/subscribe/ws` and `WS /rpc/gossip/ws?topic=` — see [websocket.md](./websocket.md).

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

- **Default**: 120 requests per 60 s **per client IP** (`RateLimitMiddleware`, `rate_limit_requests`/`rate_limit_window_seconds` settings)
- **Disable**: `AITBC_ENABLE_RATE_LIMITING=false` outside production; production cannot disable it
- Exceeding the limit returns `429`

## SDK Coverage

**There is no SDK client for the market operations above.** Resource discovery, bidding
and pricing are available over HTTP only — use the endpoints documented in this file.

`aitbc-agent-sdk` (`packages/py/aitbc-agent-sdk`) covers the neighbouring job workflow, not
the market:

```python
from aitbc_agent import ComputeConsumer

consumer = ComputeConsumer.create(
    name="my-consumer",
    agent_type="consumer",
    capabilities={"compute_type": "inference"},
)

job_id = await consumer.submit_job(
    job_type="llm_inference",
    input_data={"model": "llama2", "prompt": "Hello"},
    requirements={"gpu_memory": 8},
    max_price=0.15,
)
status = await consumer.get_job_status(job_id)
```

`Agent.get_reputation()` returns the calling agent's own reputation and takes no arguments;
it cannot query another agent. Use the [Reputation](#reputation) endpoints for that.

See [Python SDK Examples](./examples/python-sdk-examples.md) for the full agent and client
SDK surface.

## Implementation Details

### Service Architecture

- **Coordinator API** (port 8203): Live job-submission/orchestration REST API; also hosts the GPU-market and reputation routers
- **Market Service** (port 8102): Business logic and matching
- **Blockchain Node** (port 8202): On-chain transactions and escrow

### Key Files

- **Market-service endpoints**: `/opt/aitbc/apps/market/src/market_service/main.py`
- **Service layer**: `/opt/aitbc/apps/market/src/market_service/services/market_service.py`
- **Matching engine**: `/opt/aitbc/apps/market/src/market_service/services/matching_service.py`
- **Coordinator GPU market**: `/opt/aitbc/apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py`
- **Coordinator reputation API**: `/opt/aitbc/apps/coordinator-api/src/coordinator_api/contexts/reputation/routers/reputation.py`

## Escrow Integration

When `POST /v1/market/offers/{offer_id}/book` is called, the market-service automatically creates a blockchain escrow to lock buyer funds. The escrow lifecycle is managed via the blockchain node RPC.

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

The escrow subcommands take a `--job-id` flag (the coordinator job ID), not a positional argument:

```bash
# Check escrow state
aitbc market escrow status --job-id job-123

# Release to provider (after job completes)
aitbc market escrow release --job-id job-123

# Refund to buyer
aitbc market escrow refund --job-id job-123 --reason buyer_requested
```

See the full [Escrow API Reference](./escrow-api.md) for direct RPC access.

## Service Architecture

| Service | Port | Role |
|---|---|---|
| `aitbc-market` | 8102 | Market offers/bids — **production** |
| `aitbc-blockchain-rpc` | 8202 | Blockchain transactions + escrow RPC |
| `aitbc-api-gateway` | 8201 | Public gateway (`/v1/market`, `/v1/escrow`) |
| `aitbc-coordinator-api` | 8203 | Job submission/orchestration — **live production API** |

## Related Documentation

- [Escrow API Reference](./escrow-api.md) - Blockchain escrow endpoints
- [Blockchain Node API](./blockchain/README.md) - Blockchain RPC reference
- [CLI Market Tools](../apps/market/CLI_TOOLS.md) - CLI command reference
- Compute Provider Agent Guide - Agent integration guide
