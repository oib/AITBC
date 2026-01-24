# Ollama GPU Inference Testing Scenario

## Overview

This document describes the complete end-to-end testing workflow for Ollama GPU inference jobs on the AITBC platform, from job submission to receipt generation.

## Test Architecture

```
Client (CLI) → Coordinator API → GPU Miner (Host) → Ollama → Receipt → Blockchain
     ↓               ↓                ↓              ↓         ↓           ↓
  Submit Job    Queue Job      Process Job    Run Model  Generate   Record Tx
  Check Status  Assign Miner  Submit Result  Metrics   Receipt    with Payment
```

## Prerequisites

### System Setup
```bash
# Repository location
cd /home/oib/windsurf/aitbc

# Virtual environment
source .venv/bin/activate

# Ensure services are running
./scripts/aitbc-cli.sh health
```

### Required Services
- Coordinator API: http://127.0.0.1:18000
- Ollama API: http://localhost:11434
- GPU Miner Service: systemd service
- Blockchain Node: http://127.0.0.1:19000

## Test Scenarios

### Scenario 1: Basic Inference Job

#### Step 1: Submit Job
```bash
./scripts/aitbc-cli.sh submit inference \
  --prompt "What is artificial intelligence?" \
  --model llama3.2:latest \
  --ttl 900

# Expected output:
# ✅ Job submitted successfully!
#    Job ID: abc123def456...
```

#### Step 2: Monitor Job Status
```bash
# Check status immediately
./scripts/aitbc-cli.sh status abc123def456

# Expected: State = RUNNING

# Monitor until completion
watch -n 2 "./scripts/aitbc-cli.sh status abc123def456"
```

#### Step 3: Verify Completion
```bash
# Once completed, check receipt
./scripts/aitbc-cli.sh receipts --job-id abc123def456

# Expected: Receipt with price > 0
```

#### Step 4: Blockchain Verification
```bash
# View on blockchain explorer
./scripts/aitbc-cli.sh browser --receipt-limit 1

# Expected: Transaction showing payment amount
```

### Scenario 2: Concurrent Jobs Test

#### Submit Multiple Jobs
```bash
# Submit 5 jobs concurrently
for i in {1..5}; do
  ./scripts/aitbc-cli.sh submit inference \
    --prompt "Explain topic $i in detail" \
    --model mistral:latest &
done

# Wait for all to submit
wait
```

#### Monitor All Jobs
```bash
# Check all active jobs
./scripts/aitbc-cli.sh admin-jobs

# Expected: Multiple RUNNING jobs, then COMPLETED
```

#### Verify All Receipts
```bash
# List recent receipts
./scripts/aitbc-cli.sh receipts --limit 5

# Expected: 5 receipts with different payment amounts
```

### Scenario 3: Model Performance Test

#### Test Different Models
```bash
# Test with various models
models=("llama3.2:latest" "mistral:latest" "deepseek-coder:6.7b-base" "qwen2.5:1.5b")

for model in "${models[@]}"; do
  echo "Testing model: $model"
  ./scripts/aitbc-cli.sh submit inference \
    --prompt "Write a Python hello world" \
    --model "$model" \
    --ttl 900
done
```

#### Compare Performance
```bash
# Check receipts for performance metrics
./scripts/aitbc-cli.sh receipts --limit 10

# Note: Different models have different processing times and costs
```

### Scenario 4: Error Handling Test

#### Test Job Expiration
```bash
# Submit job with very short TTL
./scripts/aitbc-cli.sh submit inference \
  --prompt "This should expire" \
  --model llama3.2:latest \
  --ttl 5

# Wait for expiration
sleep 10

# Check status
./scripts/aitbc-cli.sh status <job_id>

# Expected: State = EXPIRED
```

#### Test Job Cancellation
```bash
# Submit job
job_id=$(./scripts/aitbc-cli.sh submit inference \
  --prompt "Cancel me" \
  --model llama3.2:latest | grep "Job ID" | awk '{print $3}')

# Cancel immediately
./scripts/aitbc-cli.sh cancel "$job_id"

# Verify cancellation
./scripts/aitbc-cli.sh status "$job_id"

# Expected: State = CANCELED
```

## Monitoring and Debugging

### Check Miner Health
```bash
# Systemd service status
sudo systemctl status aitbc-host-gpu-miner.service

# Real-time logs
sudo journalctl -u aitbc-host-gpu-miner.service -f

# Manual run for debugging
python3 scripts/gpu/gpu_miner_host.py
```

### Verify Ollama Integration
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Test Ollama directly
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:latest", "prompt": "Hello", "stream": false}'
```

### Check Coordinator API
```bash
# Health check
curl http://127.0.0.1:18000/v1/health

# List registered miners
curl -H "X-Api-Key: REDACTED_ADMIN_KEY" \
  http://127.0.0.1:18000/v1/admin/miners

# List all jobs
curl -H "X-Api-Key: REDACTED_ADMIN_KEY" \
  http://127.0.0.1:18000/v1/admin/jobs
```

## Expected Results

### Successful Job Flow
1. **Submission**: Job ID returned, state = QUEUED
2. **Acquisition**: Miner picks up job, state = RUNNING
3. **Processing**: Ollama runs inference (visible in logs)
4. **Completion**: Miner submits result, state = COMPLETED
5. **Receipt**: Generated with:
   - units: Processing time in seconds
   - unit_price: 0.02 AITBC/second (default)
   - price: Total payment (units × unit_price)
6. **Blockchain**: Transaction recorded with payment

### Sample Receipt
```json
{
  "receipt_id": "abc123...",
  "job_id": "def456...",
  "provider": "REDACTED_MINER_KEY",
  "client": "REDACTED_CLIENT_KEY",
  "status": "completed",
  "units": 2.5,
  "unit_type": "gpu_seconds",
  "unit_price": 0.02,
  "price": 0.05,
  "signature": "0x..."
}
```

## Common Issues and Solutions

### Jobs Stay RUNNING
- **Cause**: Miner not running or not polling
- **Solution**: Check miner service status and logs
- **Command**: `sudo systemctl restart aitbc-host-gpu-miner.service`

### No Payment in Receipt
- **Cause**: Missing metrics in job result
- **Solution**: Ensure miner submits duration/units
- **Check**: `./scripts/aitbc-cli.sh receipts --job-id <id>`

### Ollama Connection Failed
- **Cause**: Ollama not running or wrong port
- **Solution**: Start Ollama service
- **Command**: `ollama serve`

### GPU Not Detected
- **Cause**: NVIDIA drivers not installed
- **Solution**: Install drivers and verify
- **Command**: `nvidia-smi`

## Performance Metrics

### Expected Processing Times
- llama3.2:latest: ~1-3 seconds per response
- mistral:latest: ~1-2 seconds per response
- deepseek-coder:6.7b-base: ~2-4 seconds per response
- qwen2.5:1.5b: ~0.5-1 second per response

### Expected Costs
- Default rate: 0.02 AITBC/second
- Typical job cost: 0.02-0.1 AITBC
- Minimum charge: 0.01 AITBC

## Automation Script

### End-to-End Test Script
```bash
#!/bin/bash
# e2e-ollama-test.sh

set -e

echo "Starting Ollama E2E Test..."

# Check prerequisites
echo "Checking services..."
./scripts/aitbc-cli.sh health

# Start miner if needed
if ! systemctl is-active --quiet aitbc-host-gpu-miner.service; then
  echo "Starting miner service..."
  sudo systemctl start aitbc-host-gpu-miner.service
fi

# Submit test job
echo "Submitting test job..."
job_id=$(./scripts/aitbc-cli.sh submit inference \
  --prompt "E2E test: What is 2+2?" \
  --model llama3.2:latest | grep "Job ID" | awk '{print $3}')

echo "Job submitted: $job_id"

# Monitor job
echo "Monitoring job..."
while true; do
  status=$(./scripts/aitbc-cli.sh status "$job_id" | grep "State" | awk '{print $2}')
  echo "Status: $status"
  
  if [ "$status" = "COMPLETED" ]; then
    echo "Job completed!"
    break
  elif [ "$status" = "FAILED" ] || [ "$status" = "CANCELED" ] || [ "$status" = "EXPIRED" ]; then
    echo "Job failed with status: $status"
    exit 1
  fi
  
  sleep 2
done

# Verify receipt
echo "Checking receipt..."
./scripts/aitbc-cli.sh receipts --job-id "$job_id"

echo "E2E test completed successfully!"
```

Run with:
```bash
chmod +x e2e-ollama-test.sh
./e2e-ollama-test.sh
```
