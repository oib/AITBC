# Pool Hub – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: Service still in design phase. Coordinator API and miner telemetry improvements will feed into pool hub scoring once implementation starts.

## Stage 1 (MVP)

- **Project Setup**
  - Initialize FastAPI project under `apps/pool-hub/src/app/` with `main.py`, `deps.py`, `registry.py`, `scoring.py`, and router modules (`miners.py`, `match.py`, `admin.py`, `health.py`).
  - Add `.env.example` defining bind host/port, DB DSN, Redis URL, coordinator shared secret, session TTLs.
  - Configure dependencies: FastAPI, uvicorn, pydantic-settings, SQLAlchemy/SQLModel, psycopg (or sqlite), redis, prometheus-client.

- **Data Layer**
  - Implement PostgreSQL schema for miners, miner status, feedback, price overrides as outlined in bootstrap doc.
  - Provide migrations or DDL scripts under `apps/pool-hub/migrations/`.

- **Registry & Scoring**
  - Build in-memory registry (with optional Redis backing) storing miner capabilities, health, and pricing.
  - Implement scoring function weighing capability fit, price, latency, trust, and load.

- **API Endpoints**
  - `POST /v1/miners/register` exchanging API key for session token, storing capability profile.
  - `POST /v1/miners/update` and `WS /v1/miners/heartbeat` for status updates.
  - `POST /v1/match` returning top K candidates for coordinator requests with explain string.
  - `POST /v1/feedback` to adjust trust and metrics.
  - `GET /v1/health` and `GET /v1/metrics` for observability.
  - Optional admin listing endpoint guarded by shared secret.

- **Rate Limiting & Security**
  - Enforce coordinator shared secret on `/v1/match`.
  - Add rate limits to registration and match endpoints.
  - Consider IP allowlist and TLS termination guidance.

- **Testing & Tooling**
  - Unit tests for scoring module, registry updates, and feedback adjustments.
  - Integration test simulating miners registering, updating, and matching.
  - Provide CLI scripts to seed mock miners for development.

## Stage 2+

- Introduce WebSocket streaming of match suggestions and commands.
- Add redis-based lease management, multi-region routing, and attested capability manifests.
- Integrate marketplace pricing data and blockchain settlement hooks.
