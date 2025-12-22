# Port Allocation Plan

This document tracks current and planned TCP port assignments across the AITBC devnet stack. Update it whenever new services are introduced or defaults change.

## Current Usage

| Port | Service | Location | Notes |
| --- | --- | --- | --- |
| 8011 | Coordinator API (dev) | `apps/coordinator-api/` | Development coordinator API with job and marketplace endpoints. |
| 8071 | Wallet Daemon API | `apps/wallet-daemon/` | REST and JSON-RPC wallet service with receipt verification. |
| 8080 | Blockchain RPC API (FastAPI) | `apps/blockchain-node/scripts/devnet_up.sh` → `python -m uvicorn aitbc_chain.app:app` | Exposes REST/WebSocket RPC endpoints for blocks, transactions, receipts. |
| 8090 | Mock Coordinator API | `apps/blockchain-node/scripts/devnet_up.sh` → `uvicorn mock_coordinator:app` | Generates synthetic coordinator/miner telemetry consumed by Grafana dashboards. |
| 8100 | Pool Hub API (planned) | `apps/pool-hub/` | FastAPI service for miner registry and matching. |
| 8900 | Coordinator API (production) | `apps/coordinator-api/` | Production-style deployment port. |
| 9090 | Prometheus | `apps/blockchain-node/observability/` | Scrapes blockchain node + mock coordinator metrics. |
| 3000 | Grafana | `apps/blockchain-node/observability/` | Visualizes metrics dashboards for blockchain and coordinator. |
| 4173 | Explorer Web (dev) | `apps/explorer-web/` | Vite dev server for blockchain explorer interface. |
| 5173 | Marketplace Web (dev) | `apps/marketplace-web/` | Vite dev server for marketplace interface. |

## Reserved / Planned Ports

- **Miner Node** – No default port (connects to coordinator via HTTP).
- **JavaScript/Python SDKs** – Client libraries, no dedicated ports.

## Guidance

- Avoid reusing the same port across services in devnet scripts to prevent binding conflicts (recent issues occurred when `8080`/`8090` were already in use).
- For production-grade environments, place HTTP services behind a reverse proxy (nginx/Traefik) and update this table with the external vs. internal port mapping.
- When adding new dashboards or exporters, note both the scrape port (Prometheus) and any UI port (Grafana/others).
- If a port is deprecated, strike it through in this table and add a note describing the migration path.
