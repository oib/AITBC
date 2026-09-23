# Blockchain Escrow API Reference

**Last Updated:** June 3, 2026
**Base URL:** `http://localhost:8202/rpc`

> **Auth:** the escrow router is key-gated at the router level — every endpoint
> below, including `GET` state reads, requires `X-API-Key: $BLOCKCHAIN_RPC_API_KEY`
> (from `/etc/aitbc/blockchain-secrets.env`).
**Service:** `aitbc-blockchain-rpc` (port 8202)

## Overview

The Escrow API provides blockchain-native escrow management for GPU marketplace jobs. Escrow is automatically created when a buyer books an offer, and released to the provider on job completion. All state is persisted to the blockchain node's `Escrow` database table.

## Escrow Lifecycle

```
created → funded → job_started → job_completed → released
                                               ↘ disputed → resolved
                 ↘ refunded
                 ↘ expired
```

## Endpoints

### Create Escrow

`POST /rpc/escrow/create`

Lock buyer funds for a marketplace job. **The request must carry a buyer-signed on-chain lock**: either a fully signed `lock_tx` object, or `lock_signature` plus the lock transaction fields, for an `ESCROW_LOCK` transaction that transfers `amount` (in compute-units) from the buyer to the **node wallet** (`NODE_WALLET_ADDRESS`, advertised in `/health` as `node_wallet`). Without it the endpoint returns `400 "escrow lock is required: provide lock_tx or lock_signature"`.

**Request Body:**

```json
{
  "job_id": "bid-abc123",
  "buyer": "0xabc1234567890abc1234567890abc123456789ab",
  "provider": "0xdef1234567890def1234567890def123456789de",
  "amount": 100,
  "lock_signature": "0x...",
  "lock_nonce": 12,
  "lock_fee": 1
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `job_id` | string | ✅ | Unique job/bid identifier |
| `buyer` | string | ✅ | Buyer wallet address (0x + 40 hex chars) |
| `provider` | string | ✅ | Provider wallet address (0x + 40 hex chars) |
| `amount` | number | ✅ | AIT tokens to lock in escrow |
| `lock_tx` | object | ⭕ | Fully signed `ESCROW_LOCK` tx (`from`=buyer, `to`=node wallet, `amount` in compute-units, `payload` with `job_id`/`provider`). Alternative to `lock_signature` |
| `lock_signature` | string | ⭕ | Buyer signature over the canonical lock tx; the server rebuilds the tx from `lock_nonce`/`lock_fee` (or current account nonce / computed fee) and verifies it |
| `lock_nonce` | int | – | Nonce for the `lock_signature` form; defaults to the buyer's current account nonce |
| `lock_fee` | int | – | Fee for the `lock_signature` form; defaults to the computed fee |
| `energy_quote` | object | – | Signed energy quote bound into the lock payload (`energy_quote_id`/`digest`) |

One of `lock_tx` or `lock_signature` is required. The server rejects locks whose `from` is not the buyer, whose `to` is not the node wallet, whose `amount` does not match, or whose payload `job_id`/`provider` mismatch — each with a specific `400`.

**Response `200 OK`:**

```json
{
  "success": true,
  "contract_id": "f3adfe6920c69422",
  "job_id": "bid-abc123",
  "buyer": "0xabc1234567890abc1234567890abc123456789ab",
  "provider": "0xdef1234567890def1234567890def123456789de",
  "amount": "100",
  "lock_tx_hash": "0x...",
  "message": "Contract created successfully"
}
```

---

### Get Escrow State

`GET /rpc/escrow/{job_id}`

Query the current state of an escrow contract.

**Path Parameters:**

- `job_id` — Job/bid ID used when creating the escrow

**Response `200 OK`:**

```json
{
  "job_id": "bid-abc123",
  "contract_id": "f3adfe6920c69422",
  "state": "created",
  "buyer": "0xabc1234567890abc1234567890abc123456789ab",
  "provider": "0xdef1234567890def1234567890def123456789de",
  "amount": "102.500",
  "released_amount": "0",
  "refunded_amount": "0",
  "created_at": "2026-06-03T09:39:56.012991",
  "released_at": null
}
```

**Escrow States:**

| State | Description |
|---|---|
| `created` | Contract created, funds locked |
| `funded` | Buyer has funded the escrow |
| `job_started` | Work has begun |
| `job_completed` | Work finished, pending release |
| `released` | Funds released to provider |
| `disputed` | Dispute raised |
| `resolved` | Dispute resolved |
| `refunded` | Funds returned to buyer |
| `expired` | Contract expired without completion |

**Response `404 Not Found`:**

```json
{
  "detail": "No escrow found for job_id=bid-abc123"
}
```

---

### Release Escrow

`POST /rpc/escrow/{job_id}/release`

Release locked funds to the provider after job completion.

**Path Parameters:**

- `job_id` — Job/bid ID of the escrow to release

**Request Body:** empty `{}`

**Response `200 OK`:**

```json
{
  "success": true,
  "contract_id": "f3adfe6920c69422",
  "job_id": "bid-abc123",
  "message": "Payment released successfully",
  "released_at": "2026-06-03T09:40:02.237174+00:00"
}
```

---

### Refund Escrow

`POST /rpc/escrow/{job_id}/refund`

Refund locked funds back to the buyer.

**Path Parameters:**

- `job_id` — Job/bid ID of the escrow to refund

**Request Body:**

```json
{
  "reason": "buyer_requested"
}
```

**Response `200 OK`:**

```json
{
  "success": true,
  "contract_id": "f3adfe6920c69422",
  "job_id": "bid-abc123",
  "message": "Contract refunded"
}
```

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error description"
}
```

| Code | Meaning |
|---|---|
| `400` | Invalid input (bad address format, missing fields, invalid amount, missing/invalid `lock_tx`/`lock_signature`) |
| `403` | Missing or invalid `X-API-Key` (router-level gate on every escrow route) |
| `404` | No escrow found for the given `job_id` |
| `409` | Escrow already locked on-chain with different parameters |
| `503` | EscrowManager not initialised, or `BLOCKCHAIN_RPC_API_KEY` unset on the node |

---

## CLI Usage

```bash
# Check escrow state for a job
aitbc market escrow status <job_id>

# Release escrow to provider
aitbc market escrow release <job_id>

# Refund escrow to buyer
aitbc market escrow refund <job_id>
aitbc market escrow refund <job_id> --reason "provider_failed"
```

---

## cURL Examples

```bash
# Create escrow (lock_signature form — or pass a fully signed "lock_tx" object)
curl -X POST http://localhost:8202/rpc/escrow/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{
    "job_id": "bid-abc123",
    "buyer": "0xabc1234567890abc1234567890abc123456789ab",
    "provider": "0xdef1234567890def1234567890def123456789de",
    "amount": 100,
    "lock_signature": "0x...",
    "lock_nonce": 12,
    "lock_fee": 1
  }'

# Check state
curl http://localhost:8202/rpc/escrow/bid-abc123 \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY"

# Release to provider
curl -X POST http://localhost:8202/rpc/escrow/bid-abc123/release \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" -d '{}'

# Refund buyer
curl -X POST http://localhost:8202/rpc/escrow/bid-abc123/refund \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"reason": "provider_failed"}'
```

---

## Architecture

```
CLI / marketplace-service
        │
        ▼ POST /rpc/escrow/create
aitbc-blockchain-rpc (port 8202)
        │
        ├── EscrowManager (contracts/escrow.py)
        │       └── In-memory contract tracking
        │
        └── Escrow DB table (base_models.py)
                └── Persistent job_id, buyer, provider, amount, released_at
```

**Auto-trigger:** When a marketplace offer is booked via `POST /v1/marketplace/offers/{offer_id}/book`, the marketplace-service automatically calls `POST /rpc/escrow/create`.

**API Gateway:** The gateway registers an `escrow` prefix (`/v1/escrow/*` → `BLOCKCHAIN_RPC_URL/rpc`), but its prefix-strip drops the `escrow` path segment, so `POST /v1/escrow/create` currently forwards to the nonexistent `/rpc/create`. Until the mapping is fixed, call the node directly (`POST :8202/rpc/escrow/create`) or use the doubled form `/v1/escrow/escrow/create`.

---

## Implementation

| Component | Path |
|---|---|
| Route handlers | `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py` |
| EscrowManager | `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py` |
| DB model | `apps/blockchain-node/src/aitbc_chain/base_models.py` (`class Escrow`, ~line 263) |
| Marketplace trigger | `apps/marketplace/src/marketplace_service/services/marketplace_service.py` |
| CLI commands | `cli/aitbc_cli/commands/market/` package (`escrow.py` et al.) |
