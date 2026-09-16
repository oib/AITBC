# AITBC API Reference

This section provides comprehensive documentation for all AITBC platform APIs.

## Available APIs

- [Coordinator API](./coordinator-api-openapi.json) - Job submission, management, and coordination
- [Blockchain Node API](./blockchain/) - Blockchain operations and queries
- [Wallet Daemon API](./wallet-openapi.json) - Wallet operations and key management

## OpenAPI Specifications

The `*-openapi.json` files in this directory are **generated from the applications**, not
written by hand. Regenerate them with `make openapi` and commit the result; a pre-commit hook
fails any commit that leaves them disagreeing with the code.

Each API includes an OpenAPI 3.1.0 specification that can be used with API documentation tools like:

- Swagger UI
- Redoc
- Postman
- API clients

## Authentication

Authentication is per-service:

- **Coordinator API (8203)**: the canonical customer credential is a wallet-signed JWT sent as `Authorization: Bearer <jwt>` (login flow issues the token). `X-Api-Key` remains accepted for service/legacy callers (e.g. miner routes via `require_miner`).
- **Blockchain node RPC (8202)**: admin/control mutations (`/rpc/contracts/deploy`, `/rpc/governance/*`, `/rpc/escrow/*` (router-level, GETs included), `/rpc/gpu/*` writes, `/rpc/identity/*`, `/rpc/importBlock`, `/rpc/chains/*`) require the `X-API-Key` header. `POST /rpc/transaction` and `POST /rpc/staking/stake` are **signature-verified** (wallet signature in the body, no API key). Node-to-hub subscription routes (`/rpc/subscribe`, `/rpc/heartbeat`) take a peer key from `BLOCKCHAIN_RPC_API_KEY_PEERS`, and `/rpc/force-sync` requires an admin-signed body.
- **Marketplace (8102)**: only the admin `POST /v1/marketplace/parameters/apply` route is key-gated (`X-Api-Key`); the rest are unauthenticated in the current deployment.

## Quick Start

### Using cURL

```bash
# Submit a job (customer JWT from the wallet-signed login flow)
curl -X POST http://localhost:8203/v1/jobs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  -d '{
    "payload": {"model": "llama2", "prompt": "Hello world"},
    "ttl_seconds": 900
  }'
```

### Using the Python SDK

`aitbc-sdk` covers health, wallet, registry, grants and signed receipts. It is synchronous
and has **no job-submission API** — submit jobs over HTTP as above, or with the async
`aitbc_agent.ComputeConsumer` from `aitbc-agent-sdk`.

```python
from aitbc_sdk import AITBCClient

with AITBCClient(base_url="http://localhost:8203", api_key="<YOUR_API_KEY>") as client:
    print(client.health().status)
    print(client.wallet.get_balance("wallet-123").balance)   # Decimal
```

Fetch and verify the receipt a job produced:

```python
from aitbc_sdk import CoordinatorReceiptClient, verify_receipt

with CoordinatorReceiptClient(base_url="http://localhost:8203", api_key="<YOUR_API_KEY>") as rc:
    receipt = rc.fetch_latest("job-123")
    if receipt is not None:
        print(verify_receipt(receipt).verified)
```

See [Python SDK Examples](./examples/python-sdk-examples.md) for the full surface.

## Rate Limiting

API endpoints may have rate limits enforced. Check the response headers for rate limit information:

- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the window resets

## Error Handling

API errors follow standard HTTP status codes:

- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Too Many Requests
- `500` - Internal Server Error

Error responses include a JSON body with details:

```json
{
  "detail": "Error message describing the issue"
}
```

## WebSocket Endpoints

WebSocket endpoints live on two services:

- **Blockchain node** (:8202): `WS /rpc/subscribe/ws` (lease-gated follower
  block subscription) and `WS /rpc/gossip/ws?topic=` (bidirectional gossip,
  validator-authenticated for restricted topics).
- **Agent coordinator** (:8107): `WS /api/v1/agent/messages/stream` and
  `WS /api/v1/agent/presence/stream` — agent messaging/presence, proxied
  under the hub nginx `/agent/` prefix.

The coordinator-api and marketplace services have no WebSocket endpoints —
poll their REST routes instead.

See [websocket.md](./websocket.md) for the full protocol.

## Versioning

API versions are specified in the URL path (e.g., `/v1/jobs`). Breaking changes will be introduced in new major versions. Minor versions may add new features without breaking existing functionality.
