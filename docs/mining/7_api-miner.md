# Miner API Reference

API reference for miner operations on the coordinator API
(`aitbc-coordinator-api`, port 8203). All routes below are implemented in
`apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py`
and are mounted under the `/v1` prefix.

## Authentication

Every miner endpoint requires miner authentication (`MinerDep`):

- **JWT** — `Authorization: Bearer <token>` with a token whose role is
  `miner`, or
- **API key** — `X-Api-Key: <key>` header (validated against the configured
  `miner_api_keys`), optionally with an `X-Miner-ID` header to set the miner
  identity explicitly.

The authenticated identity (`sub`) is used as the miner ID for register,
heartbeat, poll, and result submission.

## Endpoints

### Register Miner

```
POST /v1/miners/register
```

Registers the miner, or refreshes its record when called again. A
`session_token` is returned.

**Request body** (`MinerRegister`):

```json
{
  "capabilities": {"gpu": "v100", "models": ["whisper-large-v3"]},
  "concurrency": 1,
  "region": "us-east",
  "wallet_address": "0x..."
}
```

- `capabilities` (object, required) — advertised hardware/model capabilities
- `concurrency` (int, default 1)
- `region` (string, optional)
- `wallet_address` (string, optional) — payout address for escrow releases.
  A miner without one cannot be matched to escrowed work.

**Response:**

```json
{
  "status": "ok",
  "session_token": "..."
}
```

### Heartbeat

```
POST /v1/miners/heartbeat
```

**Request body** (`MinerHeartbeat`, all fields optional):

```json
{
  "inflight": 0,
  "status": "ONLINE",
  "metadata": {},
  "architecture": "x86_64",
  "edge_optimized": false,
  "network_latency_ms": 12.5
}
```

**Response:** `{"status": "ok"}` — or `404` if the miner is not registered.

### Poll for Work

```
POST /v1/miners/poll
```

**Request body** (`PollRequest`):

```json
{"max_wait_seconds": 15}
```

**Response:** `200` with an assigned job (`AssignedJob`), or `204 No Content`
when nothing is available within the wait window.

```json
{
  "job_id": "job_abc123",
  "payload": {"model": "whisper-large-v3", "input": "..."},
  "constraints": {"gpu": "v100", "min_vram_gb": 16}
}
```

### Submit Job Result

```
POST /v1/miners/{job_id}/result
```

Primary completion path: records the result, creates and signs a receipt, and
drives escrow settlement (ZK-proof and TEE-attestation gates may apply to
high-value or confidential jobs).

**Request body** (`JobResultSubmit`):

```json
{
  "result": {"output": "...", "execution_time": 600},
  "metrics": {"duration_ms": 600000},
  "tee_attestation_id": null,
  "tee_quote": null
}
```

**Response:** `{"status": "ok", "receipt": {...}}`

### Report Job Failure

```
POST /v1/miners/{job_id}/fail
POST /v1/miners/{miner_id}/jobs/{job_id}/fail
```

**Request body** (`JobFailSubmit`):

```json
{
  "error_code": "OOM",
  "error_message": "CUDA out of memory",
  "metrics": {}
}
```

**Response:** `{"status": "ok"}` (first form) or
`{"job_id": "...", "status": "failed"}` (second form).

### Complete Job (alternate)

```
POST /v1/miners/{miner_id}/jobs/{job_id}/complete
```

An alternate completion path that submits execution output plus an optional
verification receipt.

**Request body:**

```json
{
  "output": {"result": "...", "execution_time": 600},
  "receipt": {"price": "0.05", "hash": "..."}
}
```

**Response:**

```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "state": "COMPLETED",
  "completed_at": "2025-01-01T00:00:00+00:00",
  "receipt_hash": "abc123..."
}
```

### List Miner Jobs

```
POST /v1/miners/{miner_id}/jobs?limit=20&offset=0
```

Query parameters: `limit` (default 20), `offset` (default 0), `job_type`,
`min_reward`, `job_status` (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`,
`CANCELED`, `EXPIRED`).

**Response:**

```json
{
  "jobs": [{"job_id": "...", "state": "COMPLETED", "..." : "..."}],
  "total": 3,
  "limit": 20,
  "offset": 0,
  "miner_id": "miner_xyz789"
}
```

### Miner Earnings

```
POST /v1/miners/{miner_id}/earnings?from_time=...&to_time=...
```

Optional `from_time` / `to_time` query parameters. Earnings amounts are
returned as decimal strings.

**Response:**

```json
{
  "miner_id": "miner_xyz789",
  "total_earnings": "50.5",
  "pending_earnings": "5.0",
  "paid_earnings": "45.5",
  "completed_jobs": 100,
  "currency": "AITBC",
  "from_time": null,
  "to_time": null,
  "earnings_history": [
    {"job_id": "job_abc123", "amount": "0.5", "currency": "AITBC", "payment_status": "released"}
  ]
}
```

### Update Capabilities

```
PUT /v1/miners/{miner_id}/capabilities
```

Takes the same `MinerRegister` body as registration.

**Response:**

```json
{
  "miner_id": "miner_xyz789",
  "status": "updated",
  "capabilities": {"gpu": "v100"},
  "session_token": "..."
}
```

### Deregister Miner

```
DELETE /v1/miners/{miner_id}
```

**Response:** `{"miner_id": "miner_xyz789", "status": "deregistered"}`

## Job Submission (clients, not miners)

Job submission is a client operation on the same service, not part of the
miner surface: `POST /v1/jobs` (client/admin auth) accepts a `JobCreate` body
(`payload`, `constraints`, `ttl_seconds`, `payment_amount`,
`payment_currency`, escrow fields, `offer_id`, `offer_quantity`) and returns a
`JobView`. Related client routes include `GET /v1/jobs/{job_id}`,
`GET /v1/jobs/{job_id}/result`, `POST /v1/jobs/{job_id}/cancel`,
`POST /v1/jobs/{job_id}/accept`, and `POST /v1/jobs/{job_id}/reject`.

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Invalid request (e.g. job cannot be completed in its current state) |
| 401/403 | Missing or invalid miner credentials |
| 404 | Miner not registered / job not found |
| 422 | Request body validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

## Rate Limits

Per-route sliding-window limits enforced by the coordinator (requests per
minute):

- 50/min — register, result submission, job fail/complete, capabilities
  update, deregister
- 100/min — heartbeat, poll
- 200/min — list jobs, earnings

## Removed endpoints

Earlier versions of this page documented `PUT /v1/miners/{miner_id}`,
`GET /v1/miners/{miner_id}/jobs/available`,
`POST /v1/miners/{miner_id}/jobs/{job_id}/accept`, and
`GET /v1/miners/{miner_id}/stats`. None of these exist in the current code —
use `PUT /v1/miners/{miner_id}/capabilities`, `POST /v1/miners/poll`, and
`POST /v1/miners/{miner_id}/earnings` respectively.

## Next

- [Miner Quick Start](../getting-started/mining/miner-quick-start.md) — Get started
- [Job Management](./3_job-management.md) — Job management
- [Monitoring](./6_monitoring.md) - Monitor your miner
