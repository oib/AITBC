---
name: aitbc-ai-operations
description: AI job operations for AITBC including job submission, monitoring, results retrieval, resource allocation testing, and AI job monitoring
category: mlops
---

# AITBC AI Operations Skill

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

## Operations

### Submit AI Job
```bash
./aitbc-cli ai-ops submit \
  --wallet <wallet_name> \
  --type <job_type> \
  --prompt <prompt> \
  --payment <payment> \
  --password <password> \
  --rpc-url http://localhost:8006
```

### Check AI Job Status
```bash
./aitbc-cli ai-ops status --job-id <job_id> --rpc-url http://localhost:8006
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
./aitbc-cli resource allocate \
  --agent-id <agent_id> \
  --gpu <gpu_count> \
  --memory <memory_mb> \
  --duration <seconds>
```

### Check Resource Status
```bash
./aitbc-cli resource status
```

### List Available Resources
```bash
./aitbc-cli resource list
```

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
python3 cli/unified_cli.py ollama gpu-test \
  --wallet genesis \
  --model llama2 \
  --prompt "test prompt" \
  --marketplace-url http://aitbc1:8102
```

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **Module:** `cli/unified_cli.py` is a module within the CLI tool for marketplace and GPU operations
- **Note:** For GPU provider operations, prefer `python3 cli/unified_cli.py` (verified working with 7 bugs fixed)
