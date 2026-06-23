---
name: aitbc-deployment
description: "Deploy and operate AITBC production services -- coordinator API, miner, edge API, monitoring."
version: 1.1.0
author: OWL
platforms: [linux]
---

# AITBC Production Deployment

## Service File Locations (UPDATED 2026-05-29)

After repo restructure, systemd service files and wrapper scripts moved from `systemd/` into `apps/<service>/`:

| Service | Service File |
|---------|-------------|
| Coordinator API | `apps/coordinator-api/aitbc-coordinator-api.service` |
| Blockchain Node | `apps/blockchain-node/aitbc-blockchain-node.service` |
| Blockchain RPC | `apps/blockchain-node/aitbc-blockchain-rpc.service` |
| Blockchain P2P | `apps/blockchain-node/aitbc-blockchain-p2p.service` |
| Blockchain Sync | `apps/blockchain-node/aitbc-blockchain-sync.service` |
| Hermes | `apps/hermes/aitbc-hermes.service` |
| Explorer | `apps/blockchain-explorer/aitbc-explorer.service` |
| Exchange | `apps/exchange/aitbc-exchange-api.service` |
| Wallet | `apps/wallet/aitbc-wallet.service` |
| AI Engine | `apps/ai-engine/aitbc-ai.service` |
| GPU Service | `apps/gpu-service/aitbc-gpu.service` |
| Marketplace | `apps/marketplace-service/aitbc-marketplace.service` |
| Agent Coordinator | `apps/agent-coordinator/aitbc-agent-coordinator.service` |
| Agent Management | `apps/agent-management/aitbc-agent-registry.service` |
| Blockchain Event Bridge | `apps/blockchain-event-bridge/aitbc-blockchain-event-bridge.service` |
| Plugin | `scripts/utils/aitbc-plugin.service` |
| Monitoring | `scripts/monitoring/aitbc-monitoring.service` |

**Old references to `systemd/aitbc-*.service` will fail.** Always use `apps/<service>/` paths.

## Services

### Coordinator API (port 8111)
```bash
# Install dependencies (use central requirements)
cd /opt/aitbc && source venv/bin/activate
pip install -r requirements.txt
pip install -e packages/py/aitbc-agent-core -e packages/py/aitbc-agent-sdk -e packages/py/aitbc-crypto -e packages/py/aitbc-sdk

# Generate secrets
bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh

# Start
ln -sf /opt/aitbc/apps/coordinator-api/aitbc-coordinator-api.service /etc/systemd/system/
systemctl daemon-reload && systemctl start aitbc-coordinator-api

# Verify
curl http://localhost:8011/health
```

### Production Miner
```bash
ln -sf /opt/aitbc/apps/ai-engine/aitbc-production-miner.service /etc/systemd/system/
systemctl daemon-reload && systemctl start aitbc-production-miner
```
**Requires:** Ollama on port 11434. Without nvidia-smi runs CPU-only.

**CRITICAL -- Miner PATH:** The systemd service MUST include system binaries:
```
Environment="PATH=/opt/aitbc/venv/bin:/usr/bin:/usr/local/bin"
```
Without `/usr/bin`, nvidia-smi is not found and miner falls back to CPU-only on GPU hosts.

**Miner registration requirements:**
- Headers: `X-Api-Key` + `X-Miner-ID`
- Body: `{"capabilities": {"cpu": true, "llm_inference": true}}` (dict, NOT list)
- Result submission: `{"result": {...}, "metrics": {...}}` with `result` as top-level key

### Edge API (port 8103)
```bash
ln -sf /opt/aitbc/apps/edge/aitbc-edge.service /etc/systemd/system/aitbc-edge.service
systemctl daemon-reload && systemctl start aitbc-edge
```
Uses SQLite (aiosqlite) for storage. Database auto-created on first run.

### Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2:3b    # 2GB, fits in 16GB VRAM
curl http://localhost:11434/api/tags
```

**Verified on RTX 4060 Ti (16GB):** llama3.2:3b runs in ~3s per inference. Models confirmed working: `llama3.2:3b` (local), `nemotron-3-super:cloud`.

### Job Type Inference (fixed commit 0a028a53)
Jobs submitted via API without explicit `type` field are now auto-inferred:
- If payload has `model` + `prompt` → type = `inference`
- No need to set `type` field manually in job submission

## API Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/jobs` | POST | Submit AI job |
| `/v1/jobs/{id}` | GET | Job status |
| `/v1/miners/register` | POST | Register (needs X-Miner-ID) |
| `/v1/miners/poll` | POST | Poll for jobs |
| `/v1/miners/heartbeat` | POST | Heartbeat |
| `/v1/miners/{id}/result` | POST | Submit result |
| `/v1/marketplace/offers` | GET | List offers |
| `/v1/marketplace/gpu/list` | GET | List GPUs |
| `/v1/marketplace/gpu/purchase` | POST | Buy GPU |

## Dependencies

Use the central requirements system:
```bash
# Core production deps
pip install -r /opt/aitbc/requirements.txt

# Dev/testing deps
pip install -r /opt/aitbc/requirements-dev.txt

# Optional modules
pip install -r /opt/aitbc/requirements-optional/ai-ml.txt
pip install -r /opt/aitbc/requirements-optional/security.txt
pip install -r /opt/aitbc/requirements-optional/testing.txt
```

## Key Pitfalls
- Miner register: capabilities as dict `{"cpu": true}`, NOT list
- Result schema: `{"result": {...}, "metrics": {...}}` with `result` as top-level key
- Systemd: symlink from `apps/<service>/aitbc-*.service` → `/etc/systemd/system/` + daemon-reload
- `aitbc` not on PATH: `ln -sf /opt/aitbc/scripts/aitbc-cli /usr/local/bin/aitbc`
- Service files are now in `apps/<service>/`, NOT in `systemd/`
