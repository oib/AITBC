# Wallet Daemon

## Purpose & Scope

Local FastAPI service that manages encrypted keys, signs transactions/receipts, and exposes wallet RPC endpoints. The code lives in `apps/wallet` (Python package `wallet_app`); it runs in production as the `aitbc-wallet` systemd unit (port 8108, `User=aitbc`, loopback-only via `WALLET_BIND_HOST`).

## Development Setup

- Create a Python virtual environment under `apps/wallet/.venv` or use Poetry.
- Install dependencies via Poetry (preferred):

  ```bash
  poetry install
  ```

- Configuration comes from environment variables read by `wallet_app/settings.py` (`HOST`, `PORT`, `WALLET_API_KEY`, `WALLET_AUTH_ENABLED`, `WALLET_BIND_HOST`, `WALLET_BIND_PORT`, `WALLET_DIR`/`AITBC_WALLET_DIR`, `BLOCKCHAIN_RPC_URL`, …). There is no `.env.example` in `apps/wallet` — create `.env` yourself or export the variables directly.
- Run the service locally:

  ```bash
  poetry run uvicorn wallet_app.main:app --host 127.0.0.1 --port 8108 --reload
  ```

  or run the module entry point directly (`python -m wallet_app.main`), which reads `WALLET_BIND_HOST`/`WALLET_BIND_PORT` (defaults `127.0.0.1:8108`).

- REST endpoints (mounted under `/v1`):
  - `GET /v1/receipts/{job_id}` (latest receipt + signature validations)
  - `GET /v1/receipts/{job_id}/history` (full history + validations)
  - `GET /v1/wallets`, `POST /v1/wallets`
  - `GET /v1/wallets/{wallet_id}/balance`
  - `POST /v1/wallets/{wallet_id}/unlock`, `POST /v1/wallets/{wallet_id}/sign`, `POST /v1/wallets/{wallet_id}/send`
  - `GET /health`
- JSON-RPC interface (`POST /rpc`):
  - Method `receipts.verify_latest`
  - Method `receipts.verify_history`
- Keystore:
  - `src/wallet_app/crypto/encryption.py` implements Argon2id + XChaCha20-Poly1305 encryption.
  - `src/wallet_app/keystore/service.py` is the in-memory keystore; `src/wallet_app/keystore/persistent_service.py` is the persistent keystore used by the REST routes.
