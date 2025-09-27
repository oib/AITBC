# Miner Node

## Purpose & Scope

Worker daemon responsible for executing compute jobs on CPU/GPU hardware, reporting telemetry, and submitting proofs back to the coordinator. See `docs/bootstrap/miner_node.md` for the detailed implementation roadmap.

## Development Setup

- Create a Python virtual environment under `apps/miner-node/.venv`.
- Install dependencies (FastAPI optional for health endpoint, `httpx`, `pydantic`, `psutil`).
- Implement the package structure described in the bootstrap guide.

## Production Deployment (systemd)

1. Copy the project to `/opt/aitbc/apps/miner-node/` on the target host.
2. Create a virtual environment and install dependencies as needed.
3. Populate `.env` with coordinator URL/API token settings.
4. Run the installer script from repo root:
   ```bash
   sudo scripts/ops/install_miner_systemd.sh
   ```
   This installs `configs/systemd/aitbc-miner.service`, reloads systemd, and enables the service.
5. Check status/logs:
   ```bash
   sudo systemctl status aitbc-miner
   journalctl -u aitbc-miner -f
   ```
