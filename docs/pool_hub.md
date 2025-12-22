# Pool Hub – Task Breakdown

## Status (2025-12-22)

- **Stage 1**: FastAPI service implemented with miner registry, scoring engine, and Redis/PostgreSQL backing stores. Service configuration API and UI added for GPU providers to select which services to offer.
- **Service Configuration**: Implemented dynamic service configuration allowing miners to enable/disable specific GPU services, set pricing, and define capabilities.

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
  - Service Configuration endpoints:
    - `GET /v1/services/` - List all service configurations for miner
    - `GET /v1/services/{type}` - Get specific service configuration
    - `POST /v1/services/{type}` - Create/update service configuration
    - `PATCH /v1/services/{type}` - Partial update
    - `DELETE /v1/services/{type}` - Delete configuration
    - `GET /v1/services/templates/{type}` - Get default templates
    - `POST /v1/services/validate/{type}` - Validate against hardware
  - UI endpoint:
    - `GET /services` - Service configuration web interface
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
