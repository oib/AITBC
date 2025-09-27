# Miner (Host Ops) – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: Infrastructure scripts pending. Runtime behavior validated through `apps/miner-node/` control loop; host installer/systemd automation still to be implemented.

## Stage 1 (MVP)

- **Installer & Scripts**
  - Finalize `/root/scripts/aitbc-miner/install_miner.sh` to install dependencies, create venv, deploy systemd unit.
  - Implement `/root/scripts/aitbc-miner/miner.sh` main loop (poll, run job, submit proof) as per bootstrap spec.
  - Ensure scripts detect GPU availability and switch between CUDA/CPU modes.

- **Configuration**
  - Define `/etc/aitbc/miner.conf` with environment-style keys (COORD_URL, WALLET_ADDR, API_KEY, MINER_ID, WORK_DIR, intervals).
  - Document configuration editing steps and permission requirements.

- **Systemd & Logging**
  - Install `aitbc-miner.service` unit with restart policy, log path, and hardening flags.
  - Provide optional logrotate config under `configs/systemd/` or `configs/security/`.

- **Mock Coordinator Integration**
  - Supply FastAPI mock coordinator (`mock_coordinator.py`) for local smoke testing.
  - Document curl or httpie commands to validate miner registration and proof submission.

- **Documentation**
  - Update `apps/miner-node/README.md` (ops section) and create runbooks under `docs/runbooks/` once available.
  - Add troubleshooting steps (GPU check, heartbeat failures, log locations).

## Stage 2+

- Harden systemd service with `ProtectSystem`, `ProtectHome`, `NoNewPrivileges` and consider non-root user.
- Add metrics integration (Prometheus exporters, GPU telemetry).
- Automate zero-downtime updates with rolling restart instructions.
