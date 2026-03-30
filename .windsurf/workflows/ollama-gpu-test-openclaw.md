---
description: OpenClaw agent workflow for complete Ollama GPU provider testing from client submission to blockchain recording
title: OpenClaw Ollama GPU Provider Test Workflow
version: 1.0
---

# OpenClaw Ollama GPU Provider Test Workflow

This OpenClaw agent workflow executes the complete end-to-end test for Ollama GPU inference jobs, including payment processing and blockchain transaction recording.

## Prerequisites

- OpenClaw 2026.3.24+ installed and gateway running
- All services running: coordinator, GPU miner, Ollama, blockchain node
- Home directory wallets configured
- Enhanced CLI with multi-wallet support

## Agent Roles

### Test Coordinator Agent
**Purpose**: Orchestrate the complete Ollama GPU test workflow
- Coordinate test execution across all services
- Monitor progress and validate results
- Handle error conditions and retry logic

### Client Agent  
**Purpose**: Simulate client submitting AI inference jobs
- Create and manage test wallets
- Submit inference requests to coordinator
- Monitor job progress and results

### Miner Agent
**Purpose**: Simulate GPU provider processing jobs
- Monitor GPU miner service status
- Track job processing and resource utilization
- Validate receipt generation and pricing

### Blockchain Agent
**Purpose**: Verify blockchain transaction recording
- Monitor blockchain for payment transactions
- Validate transaction confirmations
- Check wallet balance updates

## OpenClaw Agent Workflow

### Phase 1: Environment Validation

```bash
# Initialize test coordinator
SESSION_ID="ollama-test-$(date +%s)"
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Initialize Ollama GPU provider test workflow. Validate all services and dependencies." \
    --thinking high

# Agent performs environment checks
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Execute environment validation: check coordinator API, Ollama service, GPU miner, blockchain node health" \
    --thinking medium
```

### Phase 2: Wallet Setup

```bash
# Initialize client agent
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Initialize as client agent. Create test wallets and configure for AI job submission." \
    --thinking medium

# Agent creates test wallets
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Create test wallets: test-client and test-miner. Switch to client wallet and verify balance." \
    --thinking medium \
    --parameters "wallet_type:simple,backup_enabled:true"

# Initialize miner agent
openclaw agent --agent miner-agent --session-id $SESSION_ID \
    --message "Initialize as miner agent. Verify miner wallet and GPU resource availability." \
    --thinking medium
```

### Phase 3: Service Health Verification

```bash
# Coordinator agent checks all services
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Perform comprehensive service health check: coordinator API, Ollama GPU service, GPU miner service, blockchain RPC" \
    --thinking high \
    --parameters "timeout:30,retry_count:3"

# Agent reports service status
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Report service health status and readiness for GPU testing" \
    --thinking medium
```

### Phase 4: GPU Test Execution

```bash
# Client agent submits inference job
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Submit Ollama GPU inference job: 'What is the capital of France?' using llama3.2:latest model" \
    --thinking high \
    --parameters "prompt:What is the capital of France?,model:llama3.2:latest,payment:10"

# Agent monitors job progress
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Monitor job progress through states: QUEUED → RUNNING → COMPLETED" \
    --thinking medium \
    --parameters "polling_interval:5,timeout:300"

# Agent validates job results
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Validate job result: 'The capital of France is Paris.' Check accuracy and completeness" \
    --thinking medium
```

### Phase 5: Payment Processing

```bash
# Client agent handles payment processing
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Process payment for completed GPU job: verify receipt information, pricing, and total cost" \
    --thinking high \
    --parameters "validate_receipt:true,check_pricing:true"

# Agent reports payment details
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Report payment details: receipt ID, provider, GPU seconds, unit price, total cost" \
    --thinking medium
```

### Phase 6: Blockchain Verification

```bash
# Blockchain agent verifies transaction recording
openclaw agent --agent blockchain-agent --session-id $SESSION_ID \
    --message "Verify blockchain transaction recording: check for payment transaction, validate confirmation, track block inclusion" \
    --thinking high \
    --parameters "confirmations:1,timeout:60"

# Agent reports blockchain status
openclaw agent --agent blockchain-agent --session-id $SESSION_ID \
    --message "Report blockchain verification results: transaction hash, block height, confirmation status" \
    --thinking medium
```

### Phase 7: Final Balance Verification

```bash
# Client agent checks final wallet balances
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Verify final wallet balances after transaction: compare initial vs final balances" \
    --thinking medium

# Miner agent checks earnings
openclaw agent --agent miner-agent --session-id $SESSION_ID \
    --message "Verify miner earnings: check wallet balance increase from GPU job payment" \
    --thinking medium
```

### Phase 8: Test Completion

```bash
# Coordinator agent generates final report
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Generate comprehensive test completion report: all phases status, results, wallet changes, blockchain verification" \
    --thinking xhigh \
    --parameters "include_metrics:true,include_logs:true,format:comprehensive"

# Agent posts results to coordination topic
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Post test results to blockchain coordination topic for permanent recording" \
    --thinking high
```

## OpenClaw Agent Templates

### Test Coordinator Agent Template

```json
{
  "name": "Ollama Test Coordinator",
  "type": "test-coordinator",
  "description": "Coordinates complete Ollama GPU provider test workflow",
  "capabilities": ["orchestration", "monitoring", "validation", "reporting"],
  "configuration": {
    "timeout": 300,
    "retry_count": 3,
    "validation_strict": true
  }
}
```

### Client Agent Template

```json
{
  "name": "AI Test Client",
  "type": "client-agent", 
  "description": "Simulates client submitting AI inference jobs",
  "capabilities": ["wallet_management", "job_submission", "payment_processing"],
  "configuration": {
    "default_model": "llama3.2:latest",
    "default_payment": 10,
    "wallet_type": "simple"
  }
}
```

### Miner Agent Template

```json
{
  "name": "GPU Test Miner",
  "type": "miner-agent",
  "description": "Monitors GPU provider and validates job processing",
  "capabilities": ["resource_monitoring", "receipt_validation", "earnings_tracking"],
  "configuration": {
    "monitoring_interval": 10,
    "gpu_utilization_threshold": 0.8
  }
}
```

### Blockchain Agent Template

```json
{
  "name": "Blockchain Verifier",
  "type": "blockchain-agent",
  "description": "Verifies blockchain transactions and confirmations",
  "capabilities": ["transaction_monitoring", "balance_tracking", "confirmation_verification"],
  "configuration": {
    "confirmations_required": 1,
    "monitoring_interval": 15
  }
}
```

## Expected Test Results

### Success Indicators

```bash
✅ Environment Check: All services healthy
✅ Wallet Setup: Test wallets created and funded
✅ Service Health: Coordinator, Ollama, GPU miner, blockchain operational
✅ GPU Test: Job submitted and completed successfully
✅ Payment Processing: Receipt generated and validated
✅ Blockchain Recording: Transaction found and confirmed
✅ Balance Verification: Wallet balances updated correctly
```

### Key Metrics

```bash
💰 Initial Wallet Balances:
   Client: 9365.0 AITBC
   Miner:  1525.0 AITBC

📤 Job Submission:
   Prompt: What is the capital of France?
   Model: llama3.2:latest
   Payment: 10 AITBC

📊 Job Result:
   Output: The capital of France is Paris.

🧾 Payment Details:
   Receipt ID: receipt_123
   Provider: miner_dev_key_1
   GPU Seconds: 45
   Unit Price: 0.02 AITBC
   Total Price: 0.9 AITBC

⛓️ Blockchain Verification:
   TX Hash: 0xabc123...
   Block: 12345
   Confirmations: 1

💰 Final Wallet Balances:
   Client: 9364.1 AITBC (-0.9 AITBC)
   Miner:  1525.9 AITBC (+0.9 AITBC)
```

## Error Handling

### Common Issues and Agent Responses

```bash
# Service Health Issues
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Service health check failed. Implementing recovery procedures: restart services, verify connectivity, check logs" \
    --thinking high

# Wallet Issues
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Wallet operation failed. Implementing wallet recovery: check keystore, verify permissions, recreate wallet if needed" \
    --thinking high

# GPU Issues
openclaw agent --agent miner-agent --session-id $SESSION_ID \
    --message "GPU processing failed. Implementing recovery: check GPU availability, restart Ollama, verify model availability" \
    --thinking high

# Blockchain Issues
openclaw agent --agent blockchain-agent --session-id $SESSION_ID \
    --message "Blockchain verification failed. Implementing recovery: check node sync, verify transaction pool, retry with different parameters" \
    --thinking high
```

## Performance Monitoring

### Agent Performance Metrics

```bash
# Monitor agent performance
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Report agent performance metrics: response time, success rate, error count, resource utilization" \
    --thinking medium

# System performance during test
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Monitor system performance during GPU test: CPU usage, memory usage, GPU utilization, network I/O" \
    --thinking medium
```

## OpenClaw Integration

### Session Management

```bash
# Create persistent session for entire test
SESSION_ID="ollama-gpu-test-$(date +%s)"

# Use session across all agents
openclaw agent --agent test-coordinator --session-id $SESSION_ID --message "Initialize test" --thinking high
openclaw agent --agent client-agent --session-id $SESSION_ID --message "Submit job" --thinking medium
openclaw agent --agent miner-agent --session-id $SESSION_ID --message "Monitor GPU" --thinking medium
openclaw agent --agent blockchain-agent --session-id $SESSION_ID --message "Verify blockchain" --thinking high
```

### Cross-Agent Communication

```bash
# Agents communicate through coordination topic
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Post coordination message: Test phase completed, next phase starting" \
    --thinking medium

# Other agents respond to coordination
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Acknowledge coordination: Ready for next phase" \
    --thinking minimal
```

## Automation Script

### Complete Test Automation

```bash
#!/bin/bash
# ollama_gpu_test_openclaw.sh

SESSION_ID="ollama-gpu-test-$(date +%s)"

echo "Starting OpenClaw Ollama GPU Provider Test..."

# Initialize coordinator
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Initialize complete Ollama GPU test workflow" \
    --thinking high

# Execute all phases automatically
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Execute complete test: environment check, wallet setup, service health, GPU test, payment processing, blockchain verification, final reporting" \
    --thinking xhigh \
    --parameters "auto_execute:true,timeout:600,report_format:comprehensive"

echo "OpenClaw Ollama GPU test completed!"
```

## Integration with Existing Workflow

### From Manual to Automated

```bash
# Manual workflow (original)
cd /home/oib/windsurf/aitbc/home
python3 test_ollama_blockchain.py

# OpenClaw automated workflow
./ollama_gpu_test_openclaw.sh
```

### Benefits of OpenClaw Integration

- **Intelligent Error Handling**: Agents detect and recover from failures
- **Adaptive Testing**: Agents adjust test parameters based on system state
- **Comprehensive Reporting**: Agents generate detailed test reports
- **Cross-Node Coordination**: Agents coordinate across multiple nodes
- **Blockchain Recording**: Results permanently recorded on blockchain

## Troubleshooting

### Agent Communication Issues

```bash
# Check OpenClaw gateway status
openclaw status --agent all

# Test agent communication
openclaw agent --agent test --message "ping" --thinking minimal

# Check session context
openclaw agent --agent test-coordinator --session-id $SESSION_ID --message "report status" --thinking medium
```

### Service Integration Issues

```bash
# Verify service endpoints
curl -s http://localhost:11434/api/tags
curl -s http://localhost:8006/health
systemctl is-active aitbc-host-gpu-miner.service

# Test CLI integration
./aitbc-cli --help
./aitbc-cli wallet info
```

This OpenClaw agent workflow transforms the manual Ollama GPU test into an intelligent, automated, and blockchain-recorded testing process with comprehensive error handling and reporting capabilities.
