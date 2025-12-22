# Coordinator API – Task Breakdown

## Status (2025-12-22)

- **Stage 1 delivery**: ✅ **DEPLOYED** - Minimal Coordinator API successfully deployed in production at https://aitbc.bubuit.net/api/v1/
  - FastAPI service running in Incus container on port 8000
  - Health endpoint operational: `/v1/health` returns `{"status":"ok","env":"container"}`
  - nginx proxy configured at `/api/v1/` route
  - Note: Full codebase has import issues, minimal version deployed
- **Testing & tooling**: Pytest suites cover job scheduling, miner flows, and receipt verification; the shared CI script `scripts/ci/run_python_tests.sh` executes these tests in GitHub Actions.
- **Documentation**: `docs/run.md` and `apps/coordinator-api/README.md` describe configuration for `RECEIPT_SIGNING_KEY_HEX` and `RECEIPT_ATTESTATION_KEY_HEX` plus the receipt history API.
- **Service APIs**: Implemented specific service endpoints for common GPU workloads (Whisper, Stable Diffusion, LLM inference, FFmpeg, Blender) with typed schemas and validation.
- **Service Registry**: Created dynamic service registry framework supporting 30+ GPU services across 6 categories (AI/ML, Media Processing, Scientific Computing, Data Analytics, Gaming, Development Tools).

## Stage 1 (MVP) - COMPLETED

- **Project Setup**
  - ✅ Initialize FastAPI app under `apps/coordinator-api/src/app/` with `main.py`, `config.py`, `deps.py`.
  - ✅ Add `.env.example` covering host/port, database URL, API key lists, rate limit configuration.
  - ✅ Create `pyproject.toml` listing FastAPI, uvicorn, pydantic, SQL driver, httpx, redis (optional).

- **Models & Persistence**
  - ✅ Design Pydantic schemas for jobs, miners, constraints, state transitions (`models.py`).
  - ✅ Implement DB layer (`db.py`) using SQLite (or Postgres) with tables for jobs, miners, sessions, worker sessions.
  - ✅ Provide migrations or schema creation script.

- **Business Logic**
  - ✅ Implement `queue.py` and `matching.py` for job scheduling.
  - ✅ Create state machine utilities (`states.py`) for job transitions.
  - ✅ Add settlement stubs in `settlement.py` for future token accounting.

- **Routers**
  - ✅ Build `/v1/jobs` endpoints (submit, get status, get result, cancel) with idempotency support.
  - ✅ Build `/v1/miners` endpoints (register, heartbeat, poll, result, fail, drain).
  - ✅ Build `/v1/admin` endpoints (stats, job listing, miner listing) with admin auth.
  - ✅ Build `/v1/services` endpoints for specific GPU workloads:
    - `/v1/services/whisper/transcribe` - Audio transcription
    - `/v1/services/stable-diffusion/generate` - Image generation
    - `/v1/services/llm/inference` - Text generation
    - `/v1/services/ffmpeg/transcode` - Video transcoding
    - `/v1/services/blender/render` - 3D rendering
  - ✅ Build `/v1/registry` endpoints for dynamic service management:
    - `/v1/registry/services` - List all available services
    - `/v1/registry/services/{id}` - Get service definition
    - `/v1/registry/services/{id}/schema` - Get JSON schema
    - `/v1/registry/services/{id}/requirements` - Get hardware requirements
  - Optionally add WebSocket endpoints under `ws/` for streaming updates.
- **Receipts & Attestations**
  - ✅ Persist signed receipts (latest + history), expose `/v1/jobs/{job_id}/receipt(s)` endpoints, and attach optional coordinator attestations when `RECEIPT_ATTESTATION_KEY_HEX` is configured.

- **Auth & Rate Limiting**
  - ✅ Implement dependencies in `deps.py` to validate API keys and optional HMAC signatures.
  - ✅ Add rate limiting (e.g., `slowapi`) per key.

- **Testing & Examples**
  - ✅ Create `.http` files or pytest suites for client/miner flows.
  - ✅ Document curl examples and quickstart instructions in `apps/coordinator-api/README.md`.

## Production Deployment Details

- **Container**: Incus container 'aitbc' at `/opt/coordinator-api/`
- **Service**: systemd service `coordinator-api.service` enabled and running
- **Port**: 8000 (internal), proxied via nginx at `/api/v1/`
- **Dependencies**: Virtual environment with FastAPI, uvicorn, pydantic installed
- **Access**: https://aitbc.bubuit.net/api/v1/health for health check
- **Note**: Full codebase has import issues, minimal version deployed with health endpoint only

## Stage 2+ - IN PROGRESS

- 🔄 Integrate with blockchain receipts for settlement triggers.
- 🔄 Add Redis-backed queues for scalability.
- 🔄 Implement metrics and tracing (Prometheus/OpenTelemetry).
- 🔄 Support multi-region coordinators with pool hub integration.
