# Miner Node – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: Core miner package (`apps/miner-node/src/aitbc_miner/`) provides registration, heartbeat, polling, and result submission flows with CLI/Python runners. Basic telemetry and tests exist; remaining tasks focus on allowlist hardening, artifact handling, and multi-slot scheduling.

## Stage 1 (MVP)

- **Package Skeleton**
  - Create Python package `aitbc_miner` with modules: `main.py`, `config.py`, `agent.py`, `probe.py`, `queue.py`, `runners/cli.py`, `runners/python.py`, `util/{fs.py, limits.py, log.py}`.
  - Add `pyproject.toml` or `requirements.txt` listing httpx, pydantic, pyyaml, psutil, uvloop (optional).

- **Configuration & Loading**
  - Implement YAML config parser supporting environment overrides (auth token, coordinator URL, heartbeat intervals, resource limits).
  - Provide `.env.example` or sample `config.yaml` in `apps/miner-node/`.

- **Capability Probe**
  - Collect CPU cores, memory, disk space, GPU info (nvidia-smi), runner availability.
  - Send capability payload to coordinator upon registration.

- **Agent Control Loop**
  - Implement async tasks for registration, heartbeat with backoff, job pulling/acking, job execution, result upload.
  - Manage workspace directories under `/var/lib/aitbc/miner/jobs/<job-id>/` with state persistence for crash recovery.

- **Runners**
  - CLI runner validating commands against allowlist definitions (`/etc/aitbc/miner/allowlist.d/`).
  - Python runner importing trusted modules from configured paths.
  - Enforce resource limits (nice, ionice, ulimit) and capture logs/metrics.

- **Result Handling**
  - Implement artifact upload via multipart requests and finalize job state with coordinator.
  - Support failure reporting with detailed error codes (E_DENY, E_OOM, E_TIMEOUT, etc.).

- **Telemetry & Health**
  - Emit structured JSON logs; optionally expose `/healthz` endpoint.
  - Track metrics: running jobs, queue length, VRAM free, CPU load.

- **Testing**
  - Provide unit tests for config loader, allowlist validator, capability probe.
  - Add integration test hitting `mock_coordinator.py` from bootstrap docs.

## Stage 2+

- Implement multi-slot scheduling (GPU vs CPU) with cgroup integration.
- Add Redis-backed queue for job retries and persistent metrics export.
- Support secure secret handling (tmpfs, hardware tokens) and network egress policies.
