# AITBC Miner – Windsurf Boot & Ops Guide

A minimal, production‑lean starter for bringing an **AITBC compute‑miner** online on Debian (Bookworm/Trixie). It is optimized for NVIDIA GPUs with CUDA support, yet safe to run CPU‑only. The miner polls jobs from a central **Coordinator API** on behalf of clients, executes AI workloads, generates proofs, and earns tokens. Payments are credited to the configured wallet.

---

## Flow Diagram
```
[ Client ] → submit job → [ Coordinator API ] → dispatch → [ Miner ] → proof → [ Coordinator API ] → credit → [ Wallet ]
```
- **Client**: User or application requesting AI computation.
- **Coordinator API**: Central dispatcher that manages jobs and miners.
- **Miner**: Executes the AI workload, generates proofs, and submits results.
- **Wallet**: Receives token rewards for completed jobs.

---

## Quickstart: Windsurf Fast Boot
The minimal info Windsurf needs to spin everything up quickly:

1. **Minimal Config Values** (edit `/etc/aitbc/miner.conf`):
   - `COORD_URL` (use mock for local dev): `http://127.0.0.1:8080`
   - `WALLET_ADDR` (any test string for mock): `wallet_demo`
   - `API_KEY` (mock ignores, still set one): `CHANGE_ME`
   - `MINER_ID`: `$(hostname)-gpu0`
2. **Dependencies**
   ```bash
   apt update
   apt install -y python3 python3-venv python3-pip curl jq ca-certificates git pciutils lsb-release
   # mock coordinator deps
   pip install fastapi uvicorn
   ```
   - **GPU optional**: ensure `nvidia-smi` works for CUDA path.
3. **Boot the Mock Coordinator** (new terminal):
   ```bash
   uvicorn mock_coordinator:app --reload --host 0.0.0.0 --port 8080
   ```
4. **Install & Start Miner**
   ```bash
   /root/scripts/aitbc-miner/install_miner.sh
   systemctl start aitbc-miner.service
   ```
5. **Verify**
   ```bash
   systemctl status aitbc-miner.service
   tail -f /var/log/aitbc-miner.log
   curl -s http://127.0.0.1:8080/v1/wallet/balance | jq
   ```

> With these details, Windsurf can boot both the miner and the mock Coordinator in under a minute without a production backend.

---

## CUDA Support
Yes, the miner supports CUDA GPUs. The installer checks for `nvidia-smi` and, if present, attempts to install PyTorch with CUDA wheels (`cu124`). At runtime, tensors are placed on `'cuda'` if `torch.cuda.is_available()` is true. If no GPU is detected, the miner automatically falls back to CPU mode.

**Prerequisites for CUDA:**
- Install NVIDIA drivers on Debian:
  ```bash
  apt install -y nvidia-driver nvidia-smi
  ```
- Optional: Install CUDA toolkit if required for advanced workloads:
  ```bash
  apt install -y nvidia-cuda-toolkit
  ```
- Verify with:
  ```bash
  nvidia-smi
  ```

Make sure drivers/toolkit are installed before running the miner installer.

---

## 1) Targets & Assumptions
- Host: Debian 12/13, root shell, `zsh` available.
- Optional GPU: NVIDIA (e.g. RTX 4060 Ti) with CUDA toolchain.
- Network egress to Coordinator API (HTTPS). No inbound ports required.
- File paths align with user conventions.

---

## 2) Directory Layout
```
/root/scripts/aitbc-miner/          # scripts
  install_miner.sh
  miner.sh
/etc/aitbc/
  miner.conf                        # runtime config (env‑like)
/var/log/aitbc-miner.log            # log file (rotated by logrotate, optional)
```

---

## 3) Config File: `/etc/aitbc/miner.conf`
Environment‑style key/values. Edit with your Coordinator endpoint and wallet/API key.

```ini
# AITBC Miner config
COORD_URL="https://coordinator.example.net"    # Coordinator base URL
WALLET_ADDR="wallet1qxy2kgdygjrsqtzq2n0yrf..." # Your payout address
API_KEY="REPLACE_WITH_WALLET_API_KEY"          # Wallet‑issued key for auth
MINER_ID="$(hostname)-gpu0"                     # Any stable node label
WORK_DIR="/tmp/aitbc-work"                      # Scratch space
HEARTBEAT_SECS=20                                # Health ping interval
JOB_POLL_SECS=3                                  # Fetch cadence
MAX_CONCURRENCY=1                                # Inference job slots
# GPU modes: auto|gpu|cpu
ACCEL_MODE="auto"
```

> **Tip:** Store secrets with `chmod 600 /etc/aitbc/miner.conf`.

---

## 4) Installer Script: `/root/scripts/aitbc-miner/install_miner.sh`

```bash
#!/bin/bash
# Script Version: 01
# Description: Install AITBC miner runtime (deps, folders, service)

set -euo pipefail

LOG_FILE=/var/log/aitbc-miner.log

mkdir -p /root/scripts/aitbc-miner /etc/aitbc
: > "$LOG_FILE"
chmod 600 "$LOG_FILE"

# Base deps
apt update
apt install -y curl jq ca-certificates coreutils procps python3 python3-venv python3-pip git \
  pciutils lsb-release

# Optional: NVIDIA CLI utils detection (no failure if absent)
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[INFO] NVIDIA detected" | tee -a "$LOG_FILE"
else
  echo "[INFO] NVIDIA not detected, will run CPU mode if configured" | tee -a "$LOG_FILE"
fi

# Python env for exemplar workloads (torch optional)
VENV_DIR=/opt/aitbc-miner/.venv
mkdir -p /opt/aitbc-miner
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Minimal runtime deps
pip install --upgrade pip wheel
# Try torch (GPU if CUDA present; fallback CPU). Best‑effort only.
python - <<'PY'
import os, sys
try:
    import subprocess
    cuda_ok = subprocess.call(["bash","-lc","nvidia-smi >/dev/null 2>&1"])==0
    pkg = "--index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio" if cuda_ok else "torch torchvision torchaudio"
    os.system(f"pip install -q {pkg}")
    print("[INFO] torch installed")
except Exception as e:
    print("[WARN] torch install skipped:", e)
PY

# Place default config if missing
CONF=/etc/aitbc/miner.conf
if [ ! -f "$CONF" ]; then
  cat >/etc/aitbc/miner.conf <<'CFG'
COORD_URL="https://coordinator.example.net"
WALLET_ADDR="wallet_demo"
API_KEY="CHANGE_ME"
MINER_ID="demo-node"
WORK_DIR="/tmp/aitbc-work"
HEARTBEAT_SECS=20
JOB_POLL_SECS=3
MAX_CONCURRENCY=1
ACCEL_MODE="auto"
CFG
  chmod 600 /etc/aitbc/miner.conf
  echo "[INFO] Wrote /etc/aitbc/miner.conf" | tee -a "$LOG_FILE"
fi

# Install service unit
cat >/etc/systemd/system/aitbc-miner.service <<'UNIT'
[Unit]
Description=AITBC Compute Miner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/root/scripts/aitbc-miner/miner.sh
Restart=always
RestartSec=3
EnvironmentFile=/etc/aitbc/miner.conf
StandardOutput=append:/var/log/aitbc-miner.log
StandardError=append:/var/log/aitbc-miner.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now aitbc-miner.service

echo "[INFO] AITBC miner installed and started" | tee -a "$LOG_FILE"
```

---

## 5) Miner Runtime: `/root/scripts/aitbc-miner/miner.sh`

```bash
#!/bin/bash
# Script Version: 01
# Description: AITBC miner main loop (poll, run, prove, earn)

set -euo pipefail

LOG_FILE=/var/log/aitbc-miner.log
: > "$LOG_FILE"

# ========
# Helpers
# ========
log(){ printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
req(){
  local method="$1" path="$2" data="${3:-}"
  local url="${COORD_URL%/}${path}"
  if [ -n "$data" ]; then
    curl -fsS -X "$method" "$url" \
      -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
      --data "$data"
  else
    curl -fsS -X "$method" "$url" -H "Authorization: Bearer $API_KEY"
  fi
}

has_gpu(){ command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; }

accel_mode(){
  case "$ACCEL_MODE" in
    gpu) has_gpu && echo gpu || echo cpu ;;
    cpu) echo cpu ;;
    auto) has_gpu && echo gpu || echo cpu ;;
    *) echo cpu ;;
  esac
}

run_job(){
  local job_json="$1"
  local job_id; job_id=$(echo "$job_json" | jq -r '.id')
  local workload; workload=$(echo "$job_json" | jq -r '.workload')
  local mode; mode=$(accel_mode)

  log "[JOB] start id=$job_id mode=$mode type=$workload"
  mkdir -p "$WORK_DIR/$job_id"

  # Example workload types: "torch_bench", "sd_infer", "llm_gen"...
  case "$workload" in
    torch_bench)
      /bin/bash -lc "source /opt/aitbc-miner/.venv/bin/activate && python - <<'PY'
import time, torch
start=time.time()
x=torch.randn(1024,1024,device='cuda' if torch.cuda.is_available() else 'cpu')
for _ in range(100): x=x@x
elapsed=time.time()-start
print(f"throughput_ops={100}, seconds={elapsed:.4f}")
PY" | tee -a "$LOG_FILE" >"$WORK_DIR/$job_id/out.txt"
      ;;
    sd_infer)
      echo "stub: run stable diffusion pipeline here" | tee -a "$LOG_FILE" >"$WORK_DIR/$job_id/out.txt"
      ;;
    llm_gen)
      echo "stub: run text generation here" | tee -a "$LOG_FILE" >"$WORK_DIR/$job_id/out.txt"
      ;;
    *)
      echo "unknown workload" >"$WORK_DIR/$job_id/out.txt" ;;
  esac

  # Build a minimal proof (hash of outputs + metrics placeholder)
  local proof; proof=$(jq -n --arg id "$job_id" \
    --arg mode "$mode" \
    --arg out_sha "$(sha256sum "$WORK_DIR/$job_id/out.txt" | awk '{print $1}')" \
    '{id:$id, mode:$mode, output_sha:$out_sha, metrics:{}}')

  req POST "/v1/miner/proof" "$proof" >/dev/null
  log "[JOB] done id=$job_id proof_submitted"
}

heartbeat(){
  local mode; mode=$(accel_mode)
  local gpu; gpu=$(has_gpu && echo 1 || echo 0)
  req POST "/v1/miner/heartbeat" "$(jq -n \
    --arg id "$MINER_ID" --arg w "$WALLET_ADDR" --arg mode "$mode" \
    --argjson gpu "$gpu" '{miner_id:$id,wallet:$w,mode:$mode,gpu:$gpu}')" >/dev/null
}

# ========
# Main Process
# ========
log "[BOOT] AITBC miner starting (id=$MINER_ID)"
mkdir -p "$WORK_DIR"

# Prime heartbeat
heartbeat || log "[WARN] initial heartbeat failed"

# Poll/execute loop
while true; do
  sleep "$JOB_POLL_SECS"
  # Opportunistic heartbeat
  heartbeat || true

  # Fetch one job
  if J=$(req GET "/v1/miner/next?miner=$MINER_ID&slots=$MAX_CONCURRENCY" 2>/dev/null); then
    echo "$J" | jq -e '.id' >/dev/null 2>&1 || continue
    run_job "$J" || log "[WARN] job failed"
  fi

done
```

Make executable:
```
chmod +x /root/scripts/aitbc-miner/install_miner.sh /root/scripts/aitbc-miner/miner.sh
```

---

## 6) Bootstrap
1. Create folders + drop the three files above.
2. Edit `/etc/aitbc/miner.conf` with real values.
3. Run installer:
   ```
   /root/scripts/aitbc-miner/install_miner.sh
   ```
4. Check status & logs:
   ```
   systemctl status aitbc-miner.service
   tail -f /var/log/aitbc-miner.log
   ```

---

## 7) Health & Debug
- Quick GPU sanity: `nvidia-smi` (optional).
- Liveness: periodic `/v1/miner/heartbeat` pings.
- Job smoke test (coordinator): ensure `/v1/miner/next` returns a JSON job.

---

## 8) Logrotate (optional)
Create `/etc/logrotate.d/aitbc-miner`:
```conf
/var/log/aitbc-miner.log {
  rotate 7
  daily
  missingok
  notifempty
  compress
  copytruncate
}
```

---

## 9) Security Notes
- Keep `API_KEY` scoped to miner ops with revocation.
- No inbound ports required; allow egress HTTPS only.
- Consider systemd `ProtectSystem=full`, `ProtectHome=yes`, `NoNewPrivileges=yes` hardening once stable.

---

## 10) Extending Workloads
- Implement real `sd_infer` (Stable Diffusion) and `llm_gen` via the venv.
- Add job-level resource caps (VRAM/CPU-time) from Coordinator parameters.
- Attach accounting metrics for reward weighting (e.g., `tokens_per_kJ` or `tokens_per_TFLOP_s`).

---

## 11) Common Commands
```
# restart after config edits
systemctl restart aitbc-miner.service

# follow logs
journalctl -u aitbc-miner -f

# disable autostart
systemctl disable --now aitbc-miner.service
```

---

## 12) Coordinator API v1 (Detailed)

This section specifies the **Miner-facing** HTTP API. All endpoints are versioned under `/v1/` and use **JSON** over **HTTPS**. Authentication is via `Authorization: Bearer <API_KEY>` issued by the wallet/coordinator.

### 12.1 Global
- **Base URL**: `${COORD_URL}` (e.g., `https://coordinator.example.net`).
- **Content-Type**: `application/json; charset=utf-8`.
- **Auth**: `Authorization: Bearer <API_KEY>` (scoped for miner ops).
- **Idempotency** *(recommended)*: `Idempotency-Key: <uuid4>` for POSTs.
- **Clock**: All timestamps are ISO‑8601 UTC (e.g., `2025-09-26T13:37:00Z`).
- **Errors**: Non‑2xx responses return a body:
  ```json
  { "error": { "code": "STRING_CODE", "message": "human readable", "details": {"field": "optional context"} } }
  ```
- **Common  HTTP codes**: `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Entity`, `429 Too Many Requests`, `500/502/503`.

---

### 12.2 Types

#### MinerCapabilities
```json
{
  "miner_id": "string",
  "mode": "gpu|cpu",
  "gpu": true,
  "concurrency": 1,
  "workloads": ["torch_bench", "sd_infer", "llm_gen"],
  "limits": {"vram_mb": 16000, "ram_mb": 32768, "max_runtime_s

