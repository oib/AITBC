# Wallet Daemon – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: Core FastAPI skeleton pending, but receipt verification utilities are now implemented in `apps/wallet-daemon/src/app/receipts/service.py` using `aitbc_sdk`. Additional REST/JSON-RPC wiring remains TODO.

## Stage 1 (MVP)

- **Project Setup**
  - Initialize FastAPI application under `apps/wallet-daemon/src/app/` with `main.py`, `settings.py`, `api_rest.py`, `api_jsonrpc.py`.
  - Create crypto and keystore modules implementing Argon2id key derivation and XChaCha20-Poly1305 encryption.
  - Add `pyproject.toml` (or `requirements.txt`) with FastAPI, uvicorn, argon2-cffi, pynacl, bech32, aiosqlite, pydantic.

- **Keystore & Security**
  - Implement encrypted wallet file format storing metadata, salt, nonce, ciphertext.
  - Provide CLI or REST endpoints to create/import wallets, unlock/lock, derive accounts.
  - Enforce unlock TTL and in-memory zeroization of sensitive data.

- **REST & JSON-RPC APIs**
  - Implement REST routes: wallet lifecycle, account derivation, signing (message/tx/receipt), mock ledger endpoints, webhooks.
  - Mirror functionality via JSON-RPC under `/rpc`.
  - Add authentication token header enforcement and rate limits on signing operations.

- **Mock Ledger**
  - Implement SQLite-backed ledger with balances and transfers for local testing.
  - Provide CLI or REST examples to query balances and submit transfers.

- **Documentation & Examples**
  - Update `apps/wallet-daemon/README.md` with setup, run instructions, and curl samples.
  - Document configuration environment variables (`WALLET_BIND`, `WALLET_PORT`, `KEYSTORE_DIR`, etc.).
- **Receipts**
  - ✅ Integrate `ReceiptVerifierService` consuming `CoordinatorReceiptClient` to fetch and validate receipts (miner + coordinator signatures).

## Stage 2+

- Add ChainAdapter interface targeting real blockchain node RPC.
  - Implement mock adapter first, followed by AITBC node adapter.
- Support hardware-backed signing (YubiKey/PKCS#11) and multi-curve support gating.
- Introduce webhook retry/backoff logic and structured logging with request IDs.
