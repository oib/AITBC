# Coordinator API – Task Breakdown

## Status (2025-09-27)

- **Stage 1 delivery**: Core FastAPI service, persistence, job lifecycle, and miner flows implemented under `apps/coordinator-api/`. Receipt signing now includes optional coordinator attestations with history retrieval endpoints.
- **Testing & tooling**: Pytest suites cover job scheduling, miner flows, and receipt verification; the shared CI script `scripts/ci/run_python_tests.sh` executes these tests in GitHub Actions.
- **Documentation**: `docs/run.md` and `apps/coordinator-api/README.md` describe configuration for `RECEIPT_SIGNING_KEY_HEX` and `RECEIPT_ATTESTATION_KEY_HEX` plus the receipt history API.

## Stage 1 (MVP)

- **Project Setup**
  - Initialize FastAPI app under `apps/coordinator-api/src/app/` with `main.py`, `config.py`, `deps.py`.
  - Add `.env.example` covering host/port, database URL, API key lists, rate limit configuration.
  - Create `pyproject.toml` (or `requirements.txt`) listing FastAPI, uvicorn, pydantic, SQL driver, httpx, redis (optional).

- **Models & Persistence**
  - Design Pydantic schemas for jobs, miners, constraints, state transitions (`models.py`).
  - Implement DB layer (`db.py`) using SQLite (or Postgres) with tables for jobs, miners, sessions, worker sessions.
  - Provide migrations or schema creation script.

- **Business Logic**
  - Implement `queue.py` and `matching.py` for job scheduling.
  - Create state machine utilities (`states.py`) for job transitions.
  - Add settlement stubs in `settlement.py` for future token accounting.

- **Routers**
  - Build `/v1/jobs` endpoints (submit, get status, get result, cancel) with idempotency support.
  - Build `/v1/miners` endpoints (register, heartbeat, poll, result, fail, drain).
  - Build `/v1/admin` endpoints (stats, job listing, miner listing) with admin auth.
  - Optionally add WebSocket endpoints under `ws/` for streaming updates.
- **Receipts & Attestations**
  - ✅ Persist signed receipts (latest + history), expose `/v1/jobs/{job_id}/receipt(s)` endpoints, and attach optional coordinator attestations when `RECEIPT_ATTESTATION_KEY_HEX` is configured.

- **Auth & Rate Limiting**
  - Implement dependencies in `deps.py` to validate API keys and optional HMAC signatures.
  - Add rate limiting (e.g., `slowapi`) per key.

- **Testing & Examples**
  - Create `.http` files or pytest suites for client/miner flows.
  - Document curl examples and quickstart instructions in `apps/coordinator-api/README.md`.

## Stage 2+

- Integrate with blockchain receipts for settlement triggers.
- Add Redis-backed queues for scalability.
- Implement metrics and tracing (Prometheus/OpenTelemetry).
- Support multi-region coordinators with pool hub integration.
