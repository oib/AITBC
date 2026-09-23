# Market Service

Decentralized market for compute resources, AI models, and software
services — listing, matching, pricing, and settlement for market
participants.

**Note:** AITBC is agent-first software. Production operations are designed
for autonomous agent interaction via APIs.

The service is `aitbc-market` (port 8102), implemented in
`apps/market/src/market_service/main.py` (FastAPI). It runs as the
`aitbc` user via the `aitbc-market.service` systemd unit.

## Health and status

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness (checks DB connectivity) |
| GET | `/live` | Liveness |
| GET | `/metrics` | Prometheus metrics |
| GET | `/v1/market/status` | Market status banner |
| GET | `/v1/market` | Market overview (offer counts, average price, regions, service types) |

## Compute offers

| Method | Path | Description |
|---|---|---|
| GET | `/v1/market/offers` | List offers. Optional filters: `status`, `region`, `gpu_model`, `chain_id` |
| POST | `/v1/market/offers` | Create an offer (free-form body; `provider` defaults from `wallet`/`metadata`) |
| GET | `/v1/market/offers/{offer_id}` | Get one offer (404 when absent) |
| GET | `/v1/market/offers/{offer_id}/history` | Offer history |
| POST | `/v1/market/offers/{offer_id}/book` | Book/purchase an offer; kicks off background escrow creation when the booking carries `wallet`/`buyer`, `provider`, and `amount`/`price` |
| POST | `/v1/market/offers/{offer_id}/cancel` | Cancel an offer (optional `?reason=`) |

## Matching and bids

| Method | Path | Description |
|---|---|---|
| POST | `/v1/market/match` | Match a compute request to the best available GPU offer. Body: `{"requirements": {...}, "max_price": ..., "preferred_region": ..., "chain_id": ...}` |
| POST | `/v1/market/bids/{bid_id}/complete` | Complete a bid after on-chain payment confirms. Body must include `tx_hash` (or `transaction_hash`) |

## Analytics and pricing

| Method | Path | Description |
|---|---|---|
| GET | `/v1/market/analytics` | Market analytics; `?period_type=` (default `daily`) |
| GET | `/v1/market/performance` | Performance metrics; `?period=` (default `daily`) |
| POST | `/v1/market/dynamic-pricing` | Suggested price from supply/demand. Query params: `offer_id`, `current_demand`, `current_supply` (all required) |

## Market jobs

First-class market jobs (IPFS rentals and software services):

| Method | Path | Description |
|---|---|---|
| POST | `/v1/market/jobs` | Create a market job + payment record |
| GET | `/v1/market/jobs` | List jobs. Filters: `buyer_address`, `provider_address`, `service_type`, `state`, `offer_id`, `limit` (default 100) |
| GET | `/v1/market/jobs/usage` | Active storage usage in bytes. Requires `buyer_address` and `offer_id` |
| GET | `/v1/market/jobs/{job_id}` | Get a job (404 when absent) |
| POST | `/v1/market/jobs/{job_id}/cancel` | Cancel a job and request a refund |
| POST | `/v1/market/jobs/{job_id}/pin-confirm` | Provider confirms content pinning (`size`, `pin_tx_hash`, `provider_confirmed`) |
| POST | `/v1/market/jobs/{job_id}/release` | Release the job's escrow payment |
| POST | `/v1/market/jobs/{job_id}/refund` | Refund the job's escrow payment |
| GET | `/v1/market/jobs/{job_id}/access` | Access metadata for the job (CID, endpoints, access key) |
| GET | `/v1/market/access/{access_key}` | Validate an access token. Requires `access_secret` query param |

## IPFS rental tokens

| Method | Path | Description |
|---|---|---|
| POST | `/v1/market/ipfs/rental-token` | Register an access token for a paid IPFS rental |
| GET | `/v1/market/ipfs/rental/{access_key}` | Validate a rental token. Requires `access_secret` query param |

## Plugins and software offers

| Method | Path | Description |
|---|---|---|
| GET | `/v1/market/plugins` | List market plugins (`?plugin_type=`, `?status=` default `approved`) |
| POST | `/v1/market/plugins` | Register a new plugin |
| GET | `/v1/market/offer` | List software offers (`?service_type=`, `?status=`) |
| POST | `/v1/market/offer` | Register or update a software offer |
| GET | `/v1/market/offer/{plugin_id}` | Get a software offer |
| DELETE | `/v1/market/offer/{plugin_id}` | Unregister a software offer |
| GET | `/v1/market/offer/{plugin_id}/health` | Software-offer health check |
| GET | `/v1/market/offer-by-id/{offer_id}` | Look up a software offer by its on-chain offer ID |

## Ratings

| Method | Path | Description |
|---|---|---|
| POST | `/v1/market/offer/{service_id}/rate` | Rate a service. Body: `{"rating": <float>, "reviewer_id": "...", "comment": ""}` |
| GET | `/v1/market/offer/{service_id}/ratings` | List ratings (`?limit=50&offset=0`) plus `avg_rating`/`rating_count` |
| GET | `/v1/market/ratings/unsynced` | Ratings not yet synced to remote nodes (`?limit=100`) |
| POST | `/v1/market/ratings/sync` | Ingest ratings pushed from a remote node (body: list of rating objects) |
| POST | `/v1/market/ratings/mark-synced` | Mark rating IDs as synced (body: list of strings) |

## Transactions and governance

| Method | Path | Description |
|---|---|---|
| POST | `/v1/transactions` | Submit a market transaction. Only `type: "market"` + `action: "offer"` is accepted |
| GET | `/v1/transactions` | List market offer transactions. Optional filters: `action`, `status`, `island_id` |
| POST | `/v1/market/parameters/apply` | Apply a governance-approved parameter change. Requires the market admin API key (`X-API-Key`). Allowed parameters: `default_chain_id`, `agent_coordinator_url`, `matching_algorithm` |

## Edge nodes

| Method | Path | Description |
|---|---|---|
| POST | `/v1/market/edge-advertise` | Register/update an edge node's GPU advertisement (`node_id`, `endpoint`, `gpu_models`, `gpu_count`, `total_vram`, `region`, `capabilities`, `gpus`) |
| GET | `/v1/market/edge-advertise` | List active edge nodes (`?region=`) |
| GET | `/v1/market/edge/{node_id}/health` | Health score for one edge node |

## Knowledge graph

| Method | Path | Description |
|---|---|---|
| POST | `/v1/knowledge-graph` | Create a knowledge graph |
| POST | `/v1/knowledge-graph/{graph_id}/nodes` | Add a node |
| POST | `/v1/knowledge-graph/{graph_id}/edges` | Add an edge |
| GET | `/v1/knowledge-graph/{graph_id}` | Query a graph |

## Rate limiting

The service applies a global `RateLimitMiddleware` keyed by client IP
(`settings.rate_limit_requests` per `settings.rate_limit_window_seconds`);
`/health`, `/ready`, `/live`, and `/metrics` are excluded.

## Removed content

Earlier versions of this page described a Vite/npm "market web" UI with
`public/mock/` fixtures, `VITE_MARKET_DATA_MODE`, and a bid form — no
such UI exists in the repository. It also pointed at endpoints that the
service does not implement: `/v1/market/stats` (use
`/v1/market/analytics` or `/v1/market`), `/v1/market/bids`
listing and `POST /v1/market/bid` (there is only
`POST /v1/market/bids/{bid_id}/complete`), `/v1/market/resources`,
`/v1/market/reputation/{id}` (reputation lives on the coordinator API,
not here), and `/v1/market/pricing` (use
`POST /v1/market/dynamic-pricing`).

See [Market Internals](../../development/5_developer-guide.md) for detailed implementation flows.
