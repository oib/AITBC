# Blockchain Operations Skill

This skill provides standardized procedures for managing AITBC blockchain nodes, verifying transactions, and optimizing mining operations, including end-to-end Ollama GPU inference testing.

## Overview

The blockchain operations skill ensures reliable management of all blockchain-related components including node synchronization, transaction processing, mining operations, and network health monitoring. It also includes comprehensive testing scenarios for Ollama-based GPU inference workflows.

## Capabilities

### Node Management
- Node deployment and configuration
- Sync status monitoring
- Peer management
- Network diagnostics

### Transaction Operations
- Transaction verification and debugging
- Gas optimization
- Batch processing
- Mempool management
- Receipt generation and verification

### Mining Operations
- Mining performance optimization
- Pool management
- Reward tracking
- Hash rate optimization
- GPU miner service management

### Ollama GPU Inference Testing
- End-to-end job submission and processing
- Miner registration and heartbeat monitoring
- Job lifecycle management (submit → running → completed)
- Receipt generation with payment amounts
- Blockchain explorer verification

### Network Health
- Network connectivity checks
- Block propagation monitoring
- Fork detection and resolution
- Consensus validation

## Common Workflows

### 1. Node Health Check
- Verify node synchronization
- Check peer connections
- Validate consensus rules
- Monitor resource usage

### 2. Transaction Debugging
- Trace transaction lifecycle
- Verify gas usage
- Check receipt status
- Debug failed transactions

### 3. Mining Optimization
- Analyze mining performance
- Optimize GPU settings
- Configure mining pools
- Monitor profitability

### 4. Network Diagnostics
- Test connectivity to peers
- Analyze block propagation
- Detect network partitions
- Validate consensus state

### 5. Ollama End-to-End Testing
```bash
# Setup environment
cd /home/oib/windsurf/aitbc
source .venv/bin/activate

# Check all services
./scripts/aitbc-cli.sh health

# Start GPU miner service
sudo systemctl restart aitbc-host-gpu-miner.service
sudo journalctl -u aitbc-host-gpu-miner.service -f

# Submit inference job
./scripts/aitbc-cli.sh submit inference \
  --prompt "Explain quantum computing" \
  --model llama3.2:latest \
  --ttl 900

# Monitor job progress
./scripts/aitbc-cli.sh status <job_id>

# View blockchain receipt
./scripts/aitbc-cli.sh browser --receipt-limit 5

# Verify payment in receipt
./scripts/aitbc-cli.sh receipts --job-id <job_id>
```

### 6. Job Lifecycle Testing
1. **Submission**: Client submits job via CLI
2. **Queued**: Job enters queue, waits for miner
3. **Acquisition**: Miner polls and acquires job
4. **Processing**: Miner runs Ollama inference
5. **Completion**: Miner submits result with metrics
6. **Receipt**: System generates signed receipt with payment
7. **Blockchain**: Transaction recorded on blockchain

### 7. Miner Service Management
```bash
# Check miner status
sudo systemctl status aitbc-host-gpu-miner.service

# View miner logs
sudo journalctl -u aitbc-host-gpu-miner.service -n 100

# Restart miner service
sudo systemctl restart aitbc-host-gpu-miner.service

# Run miner manually for debugging
python3 scripts/gpu/gpu_miner_host.py

# Check registered miners
./scripts/aitbc-cli.sh admin-miners

# View active jobs
./scripts/aitbc-cli.sh admin-jobs
```

## Testing Scenarios

### Basic Inference Test
```bash
# Submit simple inference
./scripts/aitbc-cli.sh submit inference \
  --prompt "Hello AITBC" \
  --model llama3.2:latest

# Expected flow:
# 1. Job submitted → RUNNING
# 2. Miner picks up job
# 3. Ollama processes inference
# 4. Job status → COMPLETED
# 5. Receipt generated with payment amount
```

### Stress Testing Multiple Jobs
```bash
# Submit multiple jobs concurrently
for i in {1..5}; do
  ./scripts/aitbc-cli.sh submit inference \
    --prompt "Test job $i: Explain AI" \
    --model mistral:latest &
done

# Monitor all jobs
./scripts/aitbc-cli.sh admin-jobs
```

### Payment Verification Test
```bash
# Submit job with specific model
./scripts/aitbc-cli.sh submit inference \
  --prompt "Detailed analysis" \
  --model deepseek-r1:14b

# After completion, check receipt
./scripts/aitbc-cli.sh receipts --limit 1

# Verify transaction on blockchain
./scripts/aitbc-cli.sh browser --receipt-limit 1

# Expected: Receipt shows units, unit_price, and total price
```

## Supporting Files

- `node-health.sh` - Comprehensive node health monitoring
- `tx-tracer.py` - Transaction tracing and debugging tool
- `mining-optimize.sh` - GPU mining optimization script
- `network-diag.py` - Network diagnostics and analysis
- `sync-monitor.py` - Real-time sync status monitor
- `scripts/gpu/gpu_miner_host.py` - Host GPU miner client with Ollama integration
- `aitbc-cli.sh` - Bash CLI wrapper for all operations
- `ollama-test-scenario.md` - Detailed Ollama testing documentation

## Usage

This skill is automatically invoked when you request blockchain-related operations such as:
- "check node status"
- "debug transaction"
- "optimize mining"
- "network diagnostics"
- "test ollama inference"
- "submit gpu job"
- "verify payment receipt"

## Safety Features

- Automatic backup of node data before operations
- Validation of all transactions before processing
- Safe mining parameter adjustments
- Rollback capability for configuration changes
- Job expiration handling (15 minutes TTL)
- Graceful miner shutdown and restart

## Prerequisites

- AITBC node installed and configured
- GPU drivers installed (for mining operations)
- Ollama installed and running with models
- Proper network connectivity
- Sufficient disk space for blockchain data
- Virtual environment with dependencies installed
- systemd service for GPU miner

## Troubleshooting

### Jobs Stuck in RUNNING
1. Check if miner is running: `sudo systemctl status aitbc-host-gpu-miner.service`
2. View miner logs: `sudo journalctl -u aitbc-host-gpu-miner.service -f`
3. Verify coordinator API: `./scripts/aitbc-cli.sh health`
4. Cancel stuck jobs: `./scripts/aitbc-cli.sh cancel <job_id>`

### No Payment in Receipt
1. Check job completed successfully
2. Verify metrics include duration or units
3. Check receipt service logs
4. Ensure miner submitted result with metrics

### Miner Not Processing Jobs
1. Restart miner service
2. Check Ollama is running: `curl http://localhost:11434/api/tags`
3. Verify GPU availability: `nvidia-smi`
4. Check miner registration: `./scripts/aitbc-cli.sh admin-miners`

## Key Components

### Coordinator API Endpoints
- POST /v1/jobs/create - Submit new job
- GET /v1/jobs/{id}/status - Check job status
- POST /v1/miners/register - Register miner
- POST /v1/miners/poll - Poll for jobs
- POST /v1/miners/{id}/result - Submit job result

### CLI Commands
- `submit` - Submit inference job
- `status` - Check job status
- `browser` - View blockchain state
- `receipts` - List payment receipts
- `admin-miners` - List registered miners
- `admin-jobs` - List all jobs
- `cancel` - Cancel stuck job

### Receipt Structure
```json
{
  "receipt_id": "...",
  "job_id": "...",
  "provider": "REDACTED_MINER_KEY",
  "client": "REDACTED_CLIENT_KEY",
  "status": "completed",
  "units": 1.234,
  "unit_type": "gpu_seconds",
  "unit_price": 0.02,
  "price": 0.02468,
  "signature": "..."
}
```
