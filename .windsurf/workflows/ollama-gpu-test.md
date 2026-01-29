---
description: Complete Ollama GPU provider test workflow from client submission to blockchain recording
---

# Ollama GPU Provider Test Workflow

This workflow executes the complete end-to-end test for Ollama GPU inference jobs, including payment processing and blockchain transaction recording.

## Prerequisites

// turbo
- Ensure all services are running: coordinator, GPU miner, Ollama, blockchain node
- Verify home directory wallets are configured

## Steps

### 1. Environment Check
```bash
# Check service health
./scripts/aitbc-cli.sh health
curl -s http://localhost:11434/api/tags
systemctl is-active aitbc-host-gpu-miner.service
```

### 2. Run Complete Test
```bash
# Execute the full workflow test
cd /home/oib/windsurf/aitbc/home
python3 test_ollama_blockchain.py
```

### 3. Verify Results
The test will display:
- Initial wallet balances
- Job submission and ID
- Real-time job progress
- Inference result from Ollama
- Receipt details with pricing
- Payment confirmation
- Final wallet balances
- Blockchain transaction status

### 4. Manual Verification (Optional)
```bash
# Check recent receipts
curl -H "X-Api-Key: REDACTED_CLIENT_KEY" \
  http://127.0.0.1:18000/v1/explorer/receipts?limit=3

# Verify blockchain transaction
curl -s http://aitbc.keisanki.net/rpc/transactions | \
  python3 -c "import sys, json; data=json.load(sys.stdin); \
    [print(f\"TX: {t['tx_hash']} - Block: {t['block_height']}\") \
    for t in data.get('transactions', [])[-5:]]"
```

## Expected Output

```
🚀 Ollama GPU Provider Test with Home Directory Users
============================================================

💰 Initial Wallet Balances:
----------------------------------------
   Client: 9365.0 AITBC
   Miner:  1525.0 AITBC

📤 Submitting Inference Job:
----------------------------------------
   Prompt: What is the capital of France?
   Model: llama3.2:latest
✅ Job submitted: <job_id>

⏳ Monitoring Job Progress:
----------------------------------------
   State: QUEUED
   State: RUNNING
   State: COMPLETED

📊 Job Result:
----------------------------------------
   Output: The capital of France is Paris.

🧾 Receipt Information:
   Receipt ID: <receipt_id>
   Provider: REDACTED_MINER_KEY
   Units: <gpu_seconds> gpu_seconds
   Unit Price: 0.02 AITBC
   Total Price: <price> AITBC

⛓️  Checking Blockchain:
----------------------------------------
✅ Transaction found on blockchain!
   TX Hash: <tx_hash>
   Block: <block_height>

💰 Final Wallet Balances:
----------------------------------------
   Client: <new_balance> AITBC
   Miner:  <new_balance> AITBC

✅ Test completed successfully!
```

## Troubleshooting

If the test fails:
1. Check GPU miner service status
2. Verify Ollama is running
3. Ensure coordinator API is accessible
4. Check wallet configurations
5. Verify blockchain node connectivity

## Related Skills

- ollama-gpu-provider - Detailed test documentation
- blockchain-operations - Blockchain node management
