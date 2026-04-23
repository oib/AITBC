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

## Development Setup

1. Create a virtual environment in `apps/coordinator-api/.venv`.
2. Install dependencies listed in `pyproject.toml` once added.
3. Run the FastAPI app via `uvicorn app.main:app --reload`.

## Configuration

Expects environment variables defined in `.env` (see `docs/bootstrap/coordinator_api.md`).

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
