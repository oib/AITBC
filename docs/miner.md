# Miner (Host Ops) – Task Breakdown

## Status (2025-12-22)

- **Stage 1**: ✅ **IMPLEMENTED** - Infrastructure scripts and runtime behavior validated through `apps/miner-node/` control loop; host installer/systemd automation implemented.

## Stage 1 (MVP) - COMPLETED

- **Installer & Scripts**
  - ✅ Finalize `/root/scripts/aitbc-miner/install_miner.sh` to install dependencies, create venv, deploy systemd unit.
  - ✅ Implement `/root/scripts/aitbc-miner/miner.sh` main loop (poll, run job, submit proof) as per bootstrap spec.
  - ✅ Ensure scripts detect GPU availability and switch between CUDA/CPU modes.

- **Configuration**
  - ✅ Define `/etc/aitbc/miner.conf` with environment-style keys (COORD_URL, WALLET_ADDR, API_KEY, MINER_ID, WORK_DIR, intervals).
  - ✅ Document configuration editing steps and permission requirements.

- **Systemd & Logging**
  - ✅ Install `aitbc-miner.service` unit with restart policy, log path, and hardening flags.
  - ✅ Provide optional logrotate config under `configs/systemd/` or `configs/security/`.

- **Mock Coordinator Integration**
  - ✅ Supply FastAPI mock coordinator (`mock_coordinator.py`) for local smoke testing.
  - ✅ Document curl or httpie commands to validate miner registration and proof submission.

- **Documentation**
  - ✅ Update `apps/miner-node/README.md` (ops section) and create runbooks under `docs/runbooks/` once available.
  - ✅ Add troubleshooting steps (GPU check, heartbeat failures, log locations).

## Implementation Status

- **Location**: `/root/scripts/aitbc-miner/` and `apps/miner-node/`
- **Features**: Installer scripts, systemd service, configuration management
- **Runtime**: Poll, execute jobs, submit proofs with GPU/CPU detection
- **Integration**: Mock coordinator for local testing
- **Deployment**: Ready for host deployment with systemd automation

## Stage 2+ - IN PROGRESS

- 🔄 Harden systemd service with `ProtectSystem`, `ProtectHome`, `NoNewPrivileges` and consider non-root user.
- 🔄 Add metrics integration (Prometheus exporters, GPU telemetry).
- 🔄 Automate zero-downtime updates with rolling restart instructions.
