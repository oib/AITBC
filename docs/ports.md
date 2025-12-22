# Port Allocation Plan

This document tracks current and planned TCP port assignments across the AITBC devnet stack. Update it whenever new services are introduced or defaults change.

## Current Usage

| Port | Service | Location | Notes |
| --- | --- | --- | --- |
| 8080 | Blockchain RPC API (FastAPI) | `apps/blockchain-node/scripts/devnet_up.sh` → `python -m uvicorn aitbc_chain.app:app` | Exposes REST/WebSocket RPC endpoints for blocks, transactions, receipts. |
| 8090 | Mock Coordinator API | `apps/blockchain-node/scripts/devnet_up.sh` → `uvicorn mock_coordinator:app` | Generates synthetic coordinator/miner telemetry consumed by Grafana dashboards. |
| 9090 | Prometheus (planned default) | `apps/blockchain-node/observability/` (targets to be wired) | Scrapes blockchain node + mock coordinator metrics. Ensure firewall allows local-only access. |
| 3000 | Grafana (planned default) | `apps/blockchain-node/observability/grafana-dashboard.json` | Visualizes metrics dashboards; behind devnet Docker compose or local binary. |

## Reserved / Planned Ports

- **Coordinator API (production)** – TBD (`8000` suggested). Align with `apps/coordinator-api/README.md` once the service runs outside mock mode.
- **Marketplace Web** – Vite dev server defaults to `5173`; document overrides when deploying behind nginx.
- **Explorer Web** – Vite dev server defaults to `4173`; ensure it does not collide with other tooling on developer machines.
- **Pool Hub API** – Reserve `8100` for the FastAPI service when devnet integration begins.

## Guidance

- Avoid reusing the same port across services in devnet scripts to prevent binding conflicts (recent issues occurred when `8080`/`8090` were already in use).
- For production-grade environments, place HTTP services behind a reverse proxy (nginx/Traefik) and update this table with the external vs. internal port mapping.
- When adding new dashboards or exporters, note both the scrape port (Prometheus) and any UI port (Grafana/others).
- If a port is deprecated, strike it through in this table and add a note describing the migration path.
