# Wallet Daemon

## Purpose & Scope

Local FastAPI service that manages encrypted keys, signs transactions/receipts, and exposes wallet RPC endpoints. Reference `docs/bootstrap/wallet_daemon.md` for the implementation plan.

## Development Setup

- Create a Python virtual environment under `apps/wallet-daemon/.venv` or use Poetry.
- Install dependencies via Poetry (preferred):
  ```bash
  poetry install
  ```
- Copy/create `.env` and configure coordinator access:
  ```bash
  cp .env.example .env  # create file if missing
  ```
  - `COORDINATOR_BASE_URL` (default `http://localhost:8011`)
  - `COORDINATOR_API_KEY` (development key to verify receipts)
- Run the service locally:
  ```bash
  poetry run uvicorn app.main:app --host 0.0.0.0 --port 8071 --reload
  ```
- REST receipt endpoints:
  - `GET /v1/receipts/{job_id}` (latest receipt + signature validations)
  - `GET /v1/receipts/{job_id}/history` (full history + validations)
- JSON-RPC interface (`POST /rpc`):
  - Method `receipts.verify_latest`
  - Method `receipts.verify_history`
- Keystore scaffolding:
  - `KeystoreService` uses Argon2id + XChaCha20-Poly1305 via `app/crypto/encryption.py` (in-memory for now).
  - Future milestones will add persistent storage and wallet lifecycle routes.
