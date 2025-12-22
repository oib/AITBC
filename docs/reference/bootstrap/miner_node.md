# miner-node/ — Worker Node Daemon for GPU/CPU Tasks

> **Goal:** Implement a Docker‑free worker daemon that connects to the Coordinator API, advertises capabilities (CPU/GPU), fetches jobs, executes them in a sandboxed workspace, and streams results/metrics back.

---

## 1) Scope & MVP

**MVP Features**
- Node registration with Coordinator (auth token + capability descriptor).
- Heartbeat & liveness (interval ± jitter, backoff on failure).
- Job fetch → ack → execute → upload result → finalize.
- Two runner types:
  - **CLI runner**: executes a provided command with arguments (whitelist‑based).
  - **Python runner**: executes a trusted task module with parameters.
- CPU/GPU capability detection (CUDA, VRAM, driver info) without Docker.
- Sandboxed working dir per job under `/var/lib/aitbc/miner/jobs/<job-id>`.
- Resource controls (nice/ionice/ulimit; optional cgroup v2 if present).
- Structured JSON logging and minimal metrics.

**Post‑MVP**
- Chunked artifact upload; resumable transfers.
- Prometheus `/metrics` endpoint (pull).
- GPU multi‑card scheduling & fractional allocation policy.
- On‑node model cache management (size, eviction, pinning).
- Signed task manifests & attestation of execution.
- Secure TMPFS for secrets; hardware key support (YubiKey).

---

## 2) High‑Level Architecture

```
client → coordinator-api → miner-node(s) → results store → coordinator-api → client
```

Miner components:
- **Agent** (control loop): registration, heartbeat, fetch/dispatch, result reporting.
- **Capability Probe**: CPU/GPU inventory (CUDA, VRAM), free RAM/disk, load.
- **Schedulers**: simple FIFO for MVP; one job per GPU or CPU slot.
- **Runners**: CLI runner & Python runner.
- **Sandbox**: working dirs, resource limits, network I/O gating (optional), file allowlist.
- **Telemetry**: JSON logs, minimal metrics; per‑job timeline.

---

## 3) Directory Layout (on node)

```
/var/lib/aitbc/miner/
  ├─ jobs/
  │   ├─ <job-id>/
  │   │   ├─ input/
  │   │   ├─ work/
  │   │   ├─ output/
  │   │   └─ logs/
  ├─ cache/            # model/assets cache (optional)
  └─ tmp/
/etc/aitbc/miner/
  ├─ config.yaml
  └─ allowlist.d/      # allowed CLI programs & argument schema snippets
/var/log/aitbc/miner/
/usr/local/lib/aitbc/miner/  # python package venv install target
```

---

## 4) Config (YAML)

```yaml
node_id: "node-<shortid>"
coordinator:
  base_url: "https://coordinator.local/api/v1"
  auth_token: "env:MINER_AUTH"        # read from env at runtime
  tls_verify: true
  timeout_s: 20

heartbeat:
  interval_s: 15
  jitter_pct: 10
  backoff:
    min_s: 5
    max_s: 120

runners:
  cli:
    enable: true
    allowlist_files:
      - "/etc/aitbc/miner/allowlist.d/ffmpeg.yaml"
      - "/etc/aitbc/miner/allowlist.d/whisper.yaml"
  python:
    enable: true
    task_paths:
      - "/usr/local/lib/aitbc/miner/tasks"
    venv: "/usr/local/lib/aitbc/miner/.venv"

resources:
  max_concurrent_cpu: 2
  max_concurrent_gpu: 1
  cpu_nice: 10
  io_class: "best-effort"
  io_level: 6
  mem_soft_mb: 16384

workspace:
  root: "/var/lib/aitbc/miner/jobs"
  keep_success: 24h
  keep_failed: 7d

logging:
  level: "info"
  json: true
  path: "/var/log/aitbc/miner/miner.jsonl"
```

---

## 5) Environment & Dependencies

- **OS:** Debian 12/13 (systemd).
- **Python:** 3.11+ in venv under `/usr/local/lib/aitbc/miner/.venv`.
- **Libraries:** `httpx`, `pydantic`, `uvloop` (optional), `pyyaml`, `psutil`.
- **GPU (optional):** NVIDIA driver installed; `nvidia-smi` available; CUDA 12.x runtime on path for GPU tasks.

**Install skeleton**
```
python3 -m venv /usr/local/lib/aitbc/miner/.venv
/usr/local/lib/aitbc/miner/.venv/bin/pip install --upgrade pip
/usr/local/lib/aitbc/miner/.venv/bin/pip install httpx pydantic pyyaml psutil uvloop
install -d /etc/aitbc/miner /var/lib/aitbc/miner/{jobs,cache,tmp} /var/log/aitbc/miner
```

---

## 6) Systemd Service

**/etc/systemd/system/aitbc-miner.service**
```
[Unit]
Description=AITBC Miner Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=MINER_AUTH=***REDACTED***
ExecStart=/usr/local/lib/aitbc/miner/.venv/bin/python -m aitbc_miner --config /etc/aitbc/miner/config.yaml
User=games
Group=games
# Lower CPU/IO priority by default
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=6
Restart=always
RestartSec=5
# Hardening
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/aitbc/miner /var/log/aitbc/miner

[Install]
WantedBy=multi-user.target
```

---

## 7) Capability Probe (sent to Coordinator)

Example payload:
```json
{
  "node_id": "node-abc123",
  "version": "0.1.0",
  "cpu": {"cores": 16, "arch": "x86_64"},
  "memory_mb": 64000,
  "disk_free_mb": 250000,
  "gpu": [
    {
      "vendor": "nvidia", "name": "RTX 4060 Ti 16GB",
      "vram_mb": 16384,
      "cuda": {"version": "12.3", "driver": "545.23.06"}
    }
  ],
  "runners": ["cli", "python"],
  "tags": ["debian", "cuda", "cpu"]
}
```

---

## 8) Coordinator API Contract (MVP)

**Endpoints (HTTPS, JSON):**
- `POST /nodes/register` → returns signed `node_token` (or 401)
- `POST /nodes/heartbeat` → `{node_id, load, free_mb, gpu_free}` → 200
- `POST /jobs/pull` → `{node_id, filters}` → `{job|none}`
- `POST /jobs/ack` → `{job_id, node_id}` → 200
- `POST /jobs/progress` → `{job_id, pct, note}` → 200
- `POST /jobs/result` → multipart (metadata.json + artifacts/*) → 200
- `POST /jobs/fail` → `{job_id, error_code, error_msg, logs_ref}` → 200

**Auth**
- Bearer token in header (Node → Coordinator): `Authorization: Bearer <node_token>`
- Coordinator signs `job.manifest` with HMAC(sha256) or Ed25519 (post‑MVP).

**Job manifest (subset)**
```json
{
  "job_id": "j-20250926-001",
  "runner": "cli",
  "requirements": {"gpu": true, "vram_mb": 12000, "cpu_threads": 4},
  "timeout_s": 3600,
  "input": {"urls": ["https://.../input1"], "inline": {"text": "..."}},
  "command": "ffmpeg",
  "args": ["-y", "-i", "input1.mp4", "-c:v", "libx264", "output.mp4"],
  "artifacts": [{"path": "output.mp4", "type": "video/mp4", "max_mb": 5000}]
}
```

---

## 9) Runner Design

### CLI Runner
- Validate `command` against allowlist (`/etc/aitbc/miner/allowlist.d/*.yaml`).
- Validate `args` against per‑tool schema (regex & size caps).
- Materialize inputs in job workspace; set `PATH`, `CUDA_VISIBLE_DEVICES`.
- Launch via `subprocess.Popen` with `preexec_fn` applying `nice`, `ionice`, `setrlimit`.
- Live‑tail stdout/stderr to `logs/exec.log`; throttle progress pings.

### Python Runner
- Import trusted module `tasks.<name>:run(**params)` from configured paths.
- Run in same venv; optional `venv per task` later.
- Enforce timeouts; capture logs; write artifacts to `output/`.

---

## 10) Resource Controls (No Docker)

- **CPU:** `nice(10)`; optional cgroups v2 CPU.max if available.
- **IO:** `ionice -c 2 -n 6` (best‑effort) for heavy disk ops.
- **Memory:** `setrlimit(RLIMIT_AS)` soft cap; kill on OOM.
- **GPU:** select by policy (least used VRAM). No hard memory partitioning in MVP.
- **Network:** allowlist outbound hosts; deny by default (optional phase‑2).

---

## 11) Job Lifecycle (State Machine)

`IDLE → PULLING → ACKED → PREP → RUNNING → UPLOADING → DONE | FAILED | RETRY_WAIT`

- Retries: exponential backoff, max N; idempotent uploads.
- On crash: on‑start recovery scans `jobs/*/state.json` and reconciles with Coordinator.

---

## 12) Logging & Metrics

- JSON lines in `/var/log/aitbc/miner/miner.jsonl` with fields: `ts, level, node_id, job_id, event, attrs{}`.
- Optional `/healthz` (HTTP) returning 200 + brief status.
- Future: Prometheus `/metrics` with gauges (queue, running, VRAM free, CPU load).

---

## 13) Security Model

- TLS required; pin CA or enable cert validation per env.
- Node bootstrap token (`MINER_AUTH`) exchanged for `node_token` at registration.
- Strict allowlist for CLI tools + args; size/time caps.
- Secrets never written to disk unencrypted; pass via env vars or in‑memory.
- Wipe workdirs on success (per policy); keep failed for triage.

---

## 14) Windsurf Implementation Plan

**Milestone 1 — Skeleton**
1. `aitbc_miner/` package: `main.py`, `config.py`, `agent.py`, `probe.py`, `runners/{cli.py, python.py}`, `util/{limits.py, fs.py, log.py}`.
2. Load YAML config, bootstrap logs, print probe JSON.
3. Implement `/healthz` (optional FastAPI or bare aiohttp) for local checks.

**Milestone 2 — Control Loop**
1. Register → store `node_token` (in memory only).
2. Heartbeat task (async), backoff on network errors.
3. Pull/ack & single‑slot executor; write state.json.

**Milestone 3 — Runners**
1. CLI allowlist loader + validator; subprocess with limits.
2. Python runner calling `tasks.example:run`.
3. Upload artifacts via multipart; handle large files with chunking stub.

**Milestone 4 — Hardening & Ops**
1. Crash recovery; cleanup policy; TTL sweeper.
2. Metrics counters; structured logging fields.
3. Systemd unit; install scripts; doc.

---

## 15) Minimal Allowlist Example (ffmpeg)

```yaml
# /etc/aitbc/miner/allowlist.d/ffmpeg.yaml
command:
  path: "/usr/bin/ffmpeg"
args:
  - ["-y"]
  - ["-i", ".+\\.(mp4|wav|mkv)$"]
  - ["-c:v", "(libx264|copy)"]
  - ["-c:a", "(aac|copy)"]
  - ["-b:v", "[1-9][0-9]{2,5}k"]
  - ["output\\.(mp4|mkv)"]
max_total_args_len: 4096
max_runtime_s: 7200
max_output_mb: 5000
```

---

## 16) Mock Coordinator (for local testing)

> Run a tiny dev server to hand out a single job and accept results.

```python
# mock_coordinator.py (FastAPI)
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel

app = FastAPI()
JOB = {
  "job_id": "j-local-1",
  "runner": "cli",
  "requirements": {"gpu": False},
  "timeout_s": 120,
  "command": "echo",
  "args": ["hello", "world"],
  "artifacts": [{"path": "output.txt", "type": "text/plain", "max_mb": 1}]
}

class PullReq(BaseModel):
    node_id: str
    filters: dict | None = None

@app.post("/api/v1/jobs/pull")
def pull(req: PullReq):
    return {"job": JOB}

@app.post("/api/v1/jobs/ack")
def ack(job_id: str, node_id: str):
    return {"ok": True}

@app.post("/api/v1/jobs/result")
def result(job_id: str = Form(...), metadata: str = Form(...), artifact: UploadFile = File(...)):
    return {"ok": True}
```

---

## 17) Developer UX (Make Targets)

```
make venv        # create venv + install deps
make run         # run miner with local config
make fmt         # ruff/black (optional)
make test        # unit tests
```

---

## 18) Operational Runbook

- **Start/Stop**: `systemctl enable --now aitbc-miner`
- **Logs**: `journalctl -u aitbc-miner -f` and `/var/log/aitbc/miner/miner.jsonl`
- **Rotate**: logrotate config (size 50M, keep 7)
- **Upgrade**: drain → stop → replace venv → start → verify heartbeat
- **Health**: `/healthz` 200 + JSON `{running, queued, cpu_load, vram_free}`

---

## 19) Failure Modes & Recovery

- **Network errors**: exponential backoff; keep heartbeat local status.
- **Job invalid**: fail fast with reason; do not retry.
- **Runner denied**: allowlist miss → fail with `E_DENY`.
- **OOM**: kill process group; mark `E_OOM`.
- **GPU unavailable**: requeue with reason `E_NOGPU`.

---

## 20) Roadmap Notes

- Binary task bundles with signed SBOM.
- Remote cache warming via Coordinator hints.
- Multi‑Queue scheduling (latency vs throughput).
- MIG/compute‑instance support if hardware allows.

---

## 21) Checklist for Windsurf

1. Create `aitbc_miner/` package skeleton with modules listed in §14.
2. Implement config loader + capability probe output.
3. Implement async agent loop: register → heartbeat → pull/ack.
4. Implement CLI runner with allowlist (§15) and exec log.
5. Implement Python runner stub (`tasks/example.py`).
6. Write result uploader (multipart) and finalize call.
7. Add systemd unit (§6) and basic install script.
8. Test end‑to‑end against `mock_coordinator.py` (§16).
9. Document log fields + troubleshooting card.
10. Add optional `/healthz` endpoint.

