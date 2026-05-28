---
name: aitbc-ai-operations
description: AI job operations for AITBC including job submission, monitoring, results retrieval, resource allocation testing, and AI job monitoring
category: mlops
---

# AITBC AI Operations Skill

**Status:** 🟡 **Procedure Validated** - Procedures accurate if dependencies and services are present

## Trigger Conditions
Activate when user requests AI operations: job submission, status monitoring, results retrieval, resource allocation testing, or AI job monitoring.

## Purpose
Submit, monitor, and optimize AITBC AI jobs with deterministic performance tracking and resource management.

## Prerequisites
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- AI services operational (Ollama, coordinator, exchange)
- Wallet with sufficient balance for job payments
- Default test wallet: "genesis" (password from `/var/lib/aitbc/keystore/.genesis_password`)
- Resource allocation system functional

## Prerequisites Check
Before proceeding, verify:
```bash
# Check service status
systemctl list-units --state=running | grep aitbc

# Check Python dependencies
source /opt/aitbc/venv/bin/activate && pip list | grep -E "fastapi|click|uvicorn"

# Verify CLI accessible
/opt/aitbc/aitbc-cli --version

# Check AI service health
curl -s http://localhost:8005/health 2>/dev/null || echo "AI service not running"

# Check wallet balance
/opt/aitbc/aitbc-cli balance --name genesis
```

## Port Reference

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8006 | Default RPC URL for CLI |
| Coordinator API | 8011 | Agent registry |
| Marketplace | 8102 | GPU compute offers |

## Operations

### Submit AI Job
```bash
cd /opt/aitbc && ./aitbc-cli ai-ops submit \
  --wallet <wallet_name> \
  --type <job_type> \
  --prompt <prompt> \
  --payment <payment> \
  --password <password> \
  --rpc-url http://localhost:8006
```

### Check AI Job Status
```bash
cd /opt/aitbc && ./aitbc-cli ai-ops status --job-id <job_id> --rpc-url http://localhost:8006
```

### Job Types
- `inference` - AI model inference
- `training` - AI model training
- `multimodal` - Multi-modal AI processing
- `ollama` - Ollama-based operations
- `streaming` - Streaming AI responses
- `monitoring` - AI system monitoring

### Resource Allocation
```bash
# Allocate resources for AI job
cd /opt/aitbc && ./aitbc-cli resource allocate \
  --agent-id <agent_id> \
  --gpu <gpu_count> \
  --memory <memory_mb> \
  --duration <seconds>
```

### Check Resource Status
```bash
cd /opt/aitbc && ./aitbc-cli resource status
```

### List Available Resources
```bash
cd /opt/aitbc && ./aitbc-cli resource list
```

## Troubleshooting: Services Not Running

If AI services are not running, follow these steps:

### 1. Check Service Status
```bash
# List all AITBC services
systemctl list-units --type=service | grep aitbc

# Check AI-specific services
systemctl status aitbc-ai-service.service 2>/dev/null || echo "AI service not installed"
systemctl status ollama.service 2>/dev/null || echo "Ollama service not installed"
```

### 2. Check Ollama Service
```bash
# Check if Ollama is running
systemctl status ollama

# Start Ollama if not running
sudo systemctl start ollama
sudo systemctl enable ollama

# Test Ollama directly
curl -s http://localhost:11434/api/tags
```

### 3. Check Coordinator API
```bash
# Check coordinator API status
systemctl status aitbc-coordinator-api.service

# Start coordinator API if not running
sudo systemctl start aitbc-coordinator-api.service
sudo systemctl enable aitbc-coordinator-api.service

# Test coordinator API health
curl -s http://localhost:8011/health
```

### 4. Check Marketplace Service
```bash
# Check marketplace status
systemctl status aitbc-marketplace.service 2>/dev/null || echo "Marketplace service not installed"

# Test marketplace health
curl -s http://localhost:8102/health
```

### 5. Check Service Logs
```bash
# View coordinator API logs
journalctl -u aitbc-coordinator-api.service -n 50 --no-pager

# View Ollama logs
journalctl -u ollama.service -n 50 --no-pager

# Follow logs in real-time
journalctl -u aitbc-coordinator-api.service -f
```

### 6. GPU Detection
```bash
# Check if GPU is available
nvidia-smi

# If nvidia-smi fails, check if NVIDIA drivers are installed
lsmod | grep nvidia

# Check CUDA installation
nvcc --version 2>/dev/null || echo "CUDA not found"
```

For detailed troubleshooting, see [Blockchain Troubleshooting](aitbc-blockchain-troubleshooting.md).

## Common Pitfalls

1. **Insufficient Wallet Balance:** Check wallet balance before job submission
2. **Invalid Job Type:** Ensure job type is valid (inference, training, multimodal, ollama, streaming, monitoring)
3. **Service Unavailability:** Verify Ollama, coordinator, and exchange services are running
4. **Resource Allocation Failures:** Check GPU and memory availability
5. **Job Timeout:** Monitor job progress and adjust timeout if needed
6. **Payment Issues:** Ensure payment amount covers job costs
7. **Invalid Job ID:** Verify job ID when checking status

## Verification Checklist
- [ ] Job submission returns valid job ID
- [ ] Job status shows correct state (submitted, processing, completed, failed)
- [ ] Resource allocation succeeds
- [ ] Job completes within expected timeframe
- [ ] Results retrieved successfully
- [ ] Payment processed correctly

## GPU Provider Testing
```bash
# Test GPU inference
cd /opt/aitbc && python3 cli/unified_cli.py ollama gpu-test \
  --wallet genesis \
  --model llama2 \
  --prompt "test prompt" \
  --marketplace-url http://localhost:8102
```

## CLI Entry Point

**Canonical CLI:** `/opt/aitbc/aitbc-cli` (wrapper script)

This is the single CLI entry point for all AITBC operations. The wrapper script loads `cli/unified_cli.py` automatically.

**Direct Python Invocation:** `python3 cli/unified_cli.py`

Use direct Python invocation for:
- GPU testing and Ollama operations
- Specific module features requiring direct access

**Usage Examples:**
```bash
# Standard operations (use wrapper)
/opt/aitbc/aitbc-cli ai-ops submit --wallet genesis --type inference --prompt "test"
/opt/aitbc/aitbc-cli resource allocate --agent-id hermes-main --gpu 1

# GPU operations (use direct Python)
python3 cli/unified_cli.py ollama gpu-test --wallet genesis --model llama2
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-ai-operations.md`
