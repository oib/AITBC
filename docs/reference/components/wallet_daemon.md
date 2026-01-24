# Wallet Daemon – Task Breakdown

## Status (2025-12-22)

- **Stage 1**: ✅ **DEPLOYED** - Wallet Daemon successfully deployed in production at https://aitbc.bubuit.net/wallet/
  - FastAPI application running in Incus container on port 8002
  - Encrypted keystore with Argon2id + XChaCha20-Poly1305 implemented
  - REST and JSON-RPC APIs operational
  - Mock ledger with SQLite backend functional
  - Receipt verification using aitbc_sdk integrated
  - nginx proxy configured at /wallet/ route

## Stage 1 (MVP) - COMPLETED

- **Project Setup**
  - ✅ Initialize FastAPI application under `apps/wallet-daemon/src/app/` with `main.py`, `settings.py`, `api_rest.py`, `api_jsonrpc.py`.
  - ✅ Create crypto and keystore modules implementing Argon2id key derivation and XChaCha20-Poly1305 encryption.
  - ✅ Add dependencies: FastAPI, uvicorn, argon2-cffi, pynacl, aitbc-sdk, aitbc-crypto, pydantic-settings.

- **Keystore & Security**
  - ✅ Implement encrypted wallet file format storing metadata, salt, nonce, ciphertext.
  - ✅ Provide REST endpoints to create/import wallets, unlock/lock, derive accounts.
  - ✅ Enforce unlock TTL and in-memory zeroization of sensitive data.

- **REST & JSON-RPC APIs**
  - ✅ Implement REST routes: wallet lifecycle, account derivation, signing (message/tx/receipt), mock ledger endpoints.
  - ✅ Mirror functionality via JSON-RPC under `/rpc`.
  - ✅ Authentication token header enforcement and rate limits on signing operations.

- **Mock Ledger**
  - ✅ Implement SQLite-backed ledger with balances and transfers for local testing.
  - ✅ Provide REST endpoints to query balances and submit transfers.

- **Documentation & Examples**
  - ✅ Update deployment documentation with systemd service and nginx proxy configuration.
  - ✅ Document production endpoints and API access via https://aitbc.bubuit.net/wallet/
- **Receipts**
  - ✅ Integrate `ReceiptVerifierService` consuming `CoordinatorReceiptClient` to fetch and validate receipts (miner + coordinator signatures).

## Production Deployment Details

- **Container**: Incus container 'aitbc' at `/opt/wallet-daemon/`
- **Service**: systemd service `wallet-daemon.service` enabled and running
- **Port**: 8002 (internal), proxied via nginx at `/wallet/`
- **Dependencies**: Virtual environment with all required packages installed
- **Access**: https://aitbc.bubuit.net/wallet/docs for API documentation

## Stage 2+ - IN PROGRESS

- Add ChainAdapter interface targeting real blockchain node RPC.
  - 🔄 Implement mock adapter first, followed by AITBC node adapter.
- Support hardware-backed signing (YubiKey/PKCS#11) and multi-curve support gating.
- Introduce webhook retry/backoff logic and structured logging with request IDs.
