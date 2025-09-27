# Coordinator API

## Purpose & Scope

FastAPI service that accepts client compute jobs, matches miners, and tracks job lifecycle for the AITBC network.

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
