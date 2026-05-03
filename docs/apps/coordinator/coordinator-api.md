# Coordinator API

## Purpose & Scope

FastAPI service that accepts client compute jobs, matches miners, and tracks job lifecycle for the AITBC network.

## Marketplace Extensions

Stage 2 introduces public marketplace endpoints exposed under `/v1/marketplace`:

- `GET /v1/marketplace/offers` – list available provider offers (filterable by status).
- `GET /v1/marketplace/stats` – aggregated supply/demand metrics surfaced in the marketplace web dashboard.
- `POST /v1/marketplace/bids` – accept bid submissions for matching (mock-friendly; returns `202 Accepted`).

These endpoints serve the `apps/marketplace-web/` dashboard via `VITE_MARKETPLACE_DATA_MODE=live`.

## Explorer Endpoints

The coordinator now exposes read-only explorer data under `/v1/explorer` for `apps/explorer-web/` live mode:

- `GET /v1/explorer/blocks` – block summaries derived from recent job activity.
- `GET /v1/explorer/transactions` – transaction-like records for coordinator jobs.
- `GET /v1/explorer/addresses` – aggregated address activity and balances.
- `GET /v1/explorer/receipts` – latest job receipts (filterable by `job_id`).

Set `VITE_DATA_MODE=live` and `VITE_COORDINATOR_API` in the explorer web app to consume these APIs.

## Blockchain Router

The blockchain router provides RPC proxy endpoints for blockchain data integration:

- `GET /v1/status` – Blockchain status (proxies to blockchain RPC `/rpc/head`)
- `GET /v1/sync-status` – Blockchain synchronization status (proxies to `/rpc/syncStatus`)
- `GET /v1/blocks/{height}` – Get block by height (proxies to `/rpc/blocks/{height}`)
- `GET /v1/blocks/hash/{block_hash}` – Get block by hash (proxies to `/rpc/blocks/hash/{block_hash}`)
- `GET /v1/transactions/{tx_hash}` – Get transaction by hash (proxies to `/rpc/transactions/{tx_hash}`)
- `GET /v1/accounts/{address}` – Get account balance and state (proxies to `/rpc/accounts/{address}`)
- `GET /v1/validators` – List validators (derived from PoA proposer)
- `GET /v1/supply` – Get token supply (calculated from genesis allocations)
- `GET /v1/state/dump` – Get state dump (recent blocks snapshot)

All endpoints use `AITBCHTTPClient` to proxy requests to the blockchain node RPC (default port 8006). When the RPC is unavailable, endpoints return mock data or error responses.

## Edge GPU Router

The edge GPU router provides GPU management endpoints using nvidia-smi for discovery:

- `GET /v1/edge-gpu/profiles` – List available GPU profiles (uses nvidia-smi to detect GPUs)
- `GET /v1/edge-gpu/metrics/{gpu_id}` – Get GPU metrics (utilization, memory, temperature via nvidia-smi)
- `POST /v1/edge-gpu/discover` – Discover and register edge GPUs for a miner
- `POST /v1/edge-gpu/optimize` – Optimize ML inference request for edge GPU
- `POST /v1/edge-gpu/metrics` – Submit GPU metrics

GPU discovery uses `subprocess` to run `nvidia-smi` commands and parse the output. Returns empty results if nvidia-smi is unavailable or no GPUs are present.

## Multi-modal RL Router

The multi-modal RL router proxies to the AI service for job management:

- `POST /v1/multi-modal-rl/jobs` – Submit a job for execution (proxies to AI service `/jobs`)
- `GET /v1/multi-modal-rl/jobs/{job_id}` – Get job status (proxies to AI service `/jobs/{job_id}`)
- `GET /v1/multi-modal-rl/jobs/{job_id}/result` – Get job result (proxies to AI service `/jobs/{job_id}/result`)
- `POST /v1/multi-modal-rl/jobs/{job_id}/cancel` – Cancel a job (proxies to AI service `/jobs/{job_id}/cancel`)
- `GET /v1/multi-modal-rl/jobs` – List jobs with filtering (proxies to AI service `/jobs`)
- `GET /v1/multi-modal-rl/health` – Health check (proxies to AI service `/health`)

All endpoints use `AITBCHTTPClient` to proxy requests to the AI service (default port 8106). When the AI service is unavailable, endpoints return error responses indicating the service is unreachable.

## Development Setup

1. Create a virtual environment in `apps/coordinator-api/.venv`.
2. Install dependencies listed in `pyproject.toml` once added.
3. Run the FastAPI app via `uvicorn app.main:app --reload`.

## Configuration

Expects environment variables defined in `.env` (see `docs/bootstrap/coordinator_api.md`).

### Database

Production deployments use PostgreSQL for persistence. Configure via:
- `DATABASE_ADAPTER=postgresql`
- `DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/aitbc_coordinator`

SQLite fallback is available for development or nodes without PostgreSQL.

### Signed receipts (optional)

- Generate an Ed25519 key:
  ```bash
  python - <<'PY'
  from nacl.signing import SigningKey
  sk = SigningKey.generate()
  print(sk.encode().hex())
  PY
  ```
- Set `RECEIPT_SIGNING_KEY_HEX` in the `.env` file to the printed hex string to enable signed receipts returned by `/v1/miners/{job_id}/result` and retrievable via `/v1/jobs/{job_id}/receipt`.
- Receipt history is available at `/v1/jobs/{job_id}/receipts` (requires client API key) and returns all stored signed payloads.
- To enable coordinator attestations, set `RECEIPT_ATTESTATION_KEY_HEX` to a separate Ed25519 private key; responses include an `attestations` array alongside the miner signature.
- Clients can verify `signature` objects using the `aitbc_crypto` package (see `protocols/receipts/spec.md`).

## Systemd

Service name: `aitbc-coordinator-api` (to be defined under `configs/systemd/`).
