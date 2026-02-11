# Miner Node – Task Breakdown

## Status (2026-01-24)

- **Stage 1**: ✅ **IMPLEMENTED** - Core miner package (`apps/miner-node/src/aitbc_miner/`) provides registration, heartbeat, polling, and result submission flows with CLI/Python runners. Basic telemetry and tests exist.
- **Host GPU Miner**: ✅ **DEPLOYED** - Real GPU miner (`gpu_miner_host.py`) running on host with RTX 4060 Ti, Ollama integration, and systemd service. Successfully processes jobs and generates receipts with payment amounts.

## Recent Updates (2026-01-24)

### Host GPU Miner Deployment
- ✅ Deployed real GPU miner on host with NVIDIA RTX 4060 Ti (16GB)
- ✅ Integrated Ollama for LLM inference across 13+ models
- ✅ Configured systemd service (`aitbc-host-gpu-miner.service`)
- ✅ Fixed miner ID configuration (${MINER_API_KEY})
- ✅ Enhanced logging with flush handlers for systemd journal visibility
- ✅ Verified end-to-end workflow: job polling → Ollama inference → result submission → receipt generation

### Performance Metrics
- Processing time: ~11-25 seconds per inference job
- GPU utilization: 7-20% during processing
- Token processing: 200+ tokens per job
- Payment calculation: 11.846 gpu_seconds @ 0.02 AITBC = 0.23692 AITBC
- Receipt signature: Ed25519 cryptographic signing

### Integration Points
- Coordinator API: http://127.0.0.1:18000 (via Incus proxy)
- Miner ID: ${MINER_API_KEY}
- Heartbeat interval: 15 seconds
- Job polling: 3-second intervals
- Result submission: JSON with metrics and execution details


## Stage 1 (MVP) - COMPLETED

- **Package Skeleton**
  - ✅ Create Python package `aitbc_miner` with modules: `main.py`, `config.py`, `agent.py`, `probe.py`, `queue.py`, `runners/cli.py`, `runners/python.py`, `util/{fs.py, limits.py, log.py}`.
  - ✅ Add `pyproject.toml` or `requirements.txt` listing httpx, pydantic, pyyaml, psutil, uvloop (optional).

- **Configuration & Loading**
  - ✅ Implement YAML config parser supporting environment overrides (auth token, coordinator URL, heartbeat intervals, resource limits).
  - ✅ Provide `.env.example` or sample `config.yaml` in `apps/miner-node/`.

- **Capability Probe**
  - ✅ Collect CPU cores, memory, disk space, GPU info (nvidia-smi), runner availability.
  - ✅ Send capability payload to coordinator upon registration.

- **Agent Control Loop**
  - ✅ Implement async tasks for registration, heartbeat with backoff, job pulling/acking, job execution, result upload.
  - ✅ Manage workspace directories under `/var/lib/aitbc/miner/jobs/<job-id>/` with state persistence for crash recovery.

- **Runners**
  - ✅ CLI runner validating commands against allowlist definitions (`/etc/aitbc/miner/allowlist.d/`).
  - ✅ Python runner importing trusted modules from configured paths.
  - ✅ Enforce resource limits (nice, ionice, ulimit) and capture logs/metrics.

- **Result Handling**
  - ✅ Implement artifact upload via multipart requests and finalize job state with coordinator.
  - ✅ Support failure reporting with detailed error codes (E_DENY, E_OOM, E_TIMEOUT, etc.).

- **Telemetry & Health**
  - ✅ Emit structured JSON logs; optionally expose `/healthz` endpoint.
  - ✅ Track metrics: running jobs, queue length, VRAM free, CPU load.

- **Testing**
  - ✅ Provide unit tests for config loader, allowlist validator, capability probe.
  - ✅ Add integration test hitting `mock_coordinator.py` from bootstrap docs.

## Implementation Status

- **Location**: `apps/miner-node/src/aitbc_miner/`
- **Features**: Registration, heartbeat, job polling, result submission
- **Runners**: CLI and Python runners with allowlist validation
- **Resource Management**: CPU, memory, disk, GPU monitoring
- **Deployment**: Ready for deployment with coordinator integration

## Stage 2+ - IN PROGRESS

- 🔄 Implement multi-slot scheduling (GPU vs CPU) with cgroup integration.
- 🔄 Add Redis-backed queue for job retries and persistent metrics export.
- 🔄 Support secure secret handling (tmpfs, hardware tokens) and network egress policies.
