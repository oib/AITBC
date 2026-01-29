---
name: ollama-gpu-provider
title: Ollama GPU Provider Complete Test Workflow
description: Complete end-to-end test workflow for Ollama GPU inference jobs including client submission, miner processing, receipt generation, payment processing, and blockchain recording
version: 2.0
author: AITBC Team
tags: [ollama, gpu, miner, testing, workflow, blockchain, payment]
---

# Ollama GPU Provider Complete Test Workflow

This skill provides a comprehensive test workflow for verifying the entire Ollama GPU inference pipeline from client job submission through blockchain transaction recording.

## Overview

The complete flow includes:
1. Client submits inference job to coordinator
2. GPU miner picks up and processes job via Ollama
3. Miner submits result with metrics
4. Coordinator generates signed receipt
5. Client processes payment to miner
6. Transaction recorded on blockchain

## Prerequisites

### Required Services
- Coordinator API running on port 18000
- GPU miner service running (`aitbc-host-gpu-miner.service`)
- Ollama service running on port 11434
- Blockchain node accessible (local: 19000 or remote: aitbc.keisanki.net/rpc)
- Home directory wallets configured

### Configuration
```bash
# Verify services
./scripts/aitbc-cli.sh health
curl -s http://localhost:11434/api/tags
systemctl status aitbc-host-gpu-miner.service
```

## Test Options

### Option 1: Basic API Test (No Payment)
```bash
# Simple test without blockchain
python3 cli/test_ollama_gpu_provider.py \
  --url http://127.0.0.1:18000 \
  --prompt "What is the capital of France?" \
  --model llama3.2:latest
```

### Option 2: Complete Workflow with Home Directory Users
```bash
# Full test with payment and blockchain
cd /home/oib/windsurf/aitbc/home
python3 test_ollama_blockchain.py
```

### Option 3: Manual Step-by-Step
```bash
# 1. Submit job
cd /home/oib/windsurf/aitbc/home
job_id=$(../cli/client.py submit inference \
  --prompt "What is the capital of France?" \
  --model llama3.2:latest | grep "Job ID" | awk '{print $3}')

# 2. Monitor progress
watch -n 2 "../cli/client.py status $job_id"

# 3. Get result and receipt
curl -H "X-Api-Key: REDACTED_CLIENT_KEY" \
  "http://127.0.0.1:18000/v1/jobs/$job_id/result" | python3 -m json.tool

# 4. Process payment (manual)
miner_addr=$(cd miner && python3 wallet.py address | grep Address | awk '{print $3}')
amount=0.05  # Based on receipt
cd client && python3 wallet.py send $amount $miner_addr "Payment for job $job_id"

# 5. Record earnings
cd ../miner && python3 wallet.py earn $amount --job $job_id --desc "Inference job"

# 6. Check blockchain
curl -s "http://aitbc.keisanki.net/rpc/transactions" | \
  python3 -c "import sys, json; data=json.load(sys.stdin); \
    [print(f\"TX: {t['tx_hash']} - Block: {t['block_height']}\") \
    for t in data.get('transactions', []) \
    if 'receipt_id' in str(t.get('payload', {}))]"
```

## Expected Results

| Step | Expected Output | Verification |
|------|----------------|--------------|
| Job Submission | Job ID returned, state = QUEUED | `client.py status` shows job |
| Processing | State → RUNNING, miner assigned | Miner logs show job pickup |
| Completion | State = COMPLETED, output received | Result endpoint returns data |
| Receipt | Generated with price > 0 | Receipt has valid signature |
| Payment | Client balance ↓, miner ↑ | Wallet balances update |
| Blockchain | Transaction recorded | TX hash searchable |

## Monitoring Commands

```bash
# Real-time miner logs
sudo journalctl -u aitbc-host-gpu-miner.service -f

# Recent receipts
curl -H "X-Api-Key: REDACTED_CLIENT_KEY" \
  http://127.0.0.1:18000/v1/explorer/receipts?limit=5

# Wallet balances
cd /home/oib/windsurf/aitbc/home && \
  echo "Client:" && cd client && python3 wallet.py balance && \
  echo "Miner:" && cd ../miner && python3 wallet.py balance

# Blockchain transactions
curl -s http://aitbc.keisanki.net/rpc/transactions | python3 -m json.tool
```

## Troubleshooting

### Job Stuck in QUEUED
```bash
# Check miner service
systemctl status aitbc-host-gpu-miner.service

# Restart if needed
sudo systemctl restart aitbc-host-gpu-miner.service

# Check miner registration
curl -H "X-Api-Key: REDACTED_ADMIN_KEY" \
  http://127.0.0.1:18000/v1/admin/miners
```

### No Receipt Generated
```bash
# Verify receipt signing key
grep receipt_signing_key_hex /opt/coordinator-api/src/.env

# Check job result for receipt
curl -H "X-Api-Key: REDACTED_CLIENT_KEY" \
  http://127.0.0.1:18000/v1/jobs/<job_id>/result | jq .receipt
```

### Payment Issues
```bash
# Check wallet addresses
cd /home/oib/windsurf/aitbc/home/client && python3 wallet.py address
cd /home/oib/windsurf/aitbc/home/miner && python3 wallet.py address

# Verify transaction
python3 wallet.py transactions
```

### Blockchain Not Recording
```bash
# Check node availability
curl -s http://aitbc.keisanki.net/rpc/health

# Search for receipt
curl -s "http://aitbc.keisanki.net/rpc/transactions" | \
  grep <receipt_id>
```

## Test Data Examples

### Sample Job Result
```json
{
  "result": {
    "output": "The capital of France is Paris.",
    "model": "llama3.2:latest",
    "tokens_processed": 8,
    "execution_time": 0.52,
    "gpu_used": true
  },
  "receipt": {
    "receipt_id": "8c4db70a1d413188681e003f0de7342f",
    "units": 2.603,
    "unit_price": 0.02,
    "price": 0.05206
  }
}
```

### Sample Blockchain Transaction
```json
{
  "tx_hash": "0xabc123...",
  "block_height": 12345,
  "sender": "aitbc18f75b7eb7e2ecc7567b6",
  "recipient": "aitbc1721d5bf8c0005ded6704",
  "amount": 0.05206,
  "payload": {
    "receipt_id": "8c4db70a1d413188681e003f0de7342f"
  }
}
```

## Integration with CI/CD

```yaml
# GitHub Actions example
- name: Run Ollama GPU Provider Test
  run: |
    cd /home/oib/windsurf/aitbc/home
    python3 test_ollama_blockchain.py --timeout 300
```

## Related Files

- `/home/oib/windsurf/aitbc/home/test_ollama_blockchain.py` - Complete test script
- `/home/oib/windsurf/aitbc/cli/test_ollama_gpu_provider.py` - Basic API test
- `/home/oib/windsurf/aitbc/.windsurf/skills/blockchain-operations/` - Blockchain management
- `/home/oib/windsurf/aitbc/docs/infrastructure.md` - Infrastructure details
