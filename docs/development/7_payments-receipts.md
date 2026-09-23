# Payments and Receipts

This guide explains how payments work on the the network and how to understand your receipts.

## Payment Flow

```
Client submits job → Job processed by miner → Receipt generated → Payment settled
```

### Step-by-Step

1. **Job Submission**: You submit a job with your prompt and parameters
2. **Miner Selection**: The Coordinator assigns your job to an available miner
3. **Processing**: The miner executes your job using their GPU
4. **Receipt Creation**: A cryptographic receipt is generated proving work completion
5. **Settlement**: the network tokens are transferred from client to miner

## Understanding Receipts

Every completed job generates a receipt containing:

| Field | Description |
|-------|-------------|
| `receipt_id` | Unique identifier for this receipt |
| `job_id` | The job this receipt is for |
| `provider` | Miner address who processed the job |
| `client` | Your address (who requested the job) |
| `units` | Compute units consumed (e.g., GPU seconds) |
| `price` | Amount paid in the network tokens |
| `model` | AI model used |
| `started_at` | When processing began |
| `completed_at` | When processing finished |
| `signature` | Cryptographic proof of authenticity |

### Example Receipt

```json
{
  "receipt_id": "rcpt-20260124-001234",
  "job_id": "job-abc123",
  "provider": "0x1d130445f7B07cF174E248653a0A8A64cb3539cC",
  "client": "0xa5bD9225593f84dE7D5eC1Ed9B7B7f5aA6d32D51",
  "units": 2.5,
  "unit_type": "gpu_seconds",
  "price": 5.0,
  "model": "llama3.2",
  "started_at": 1737730800,
  "completed_at": 1737730803,
  "signature": {
    "alg": "Ed25519",
    "key_id": "miner-ed25519-2026-01",
    "sig": "Fql0..."
  }
}
```

## Viewing Your Receipts

### Explorer

Visit the explorer on any node (port 8100 — e.g. `http://<node>:8100/#/receipts`; the public hub explorer is `https://hub.aitbc.bubuit.net/explorer/`) to see:

- All recent receipts on the network
- Filter by your address to see your history
- Click any receipt for full details

### CLI

There is no dedicated `aitbc receipts` command. Query the coordinator API through the generic HTTP pivot (`aitbc http call`) or with `curl`:

```bash
# List receipts (optionally filter by job)
aitbc http call coordinator-api v1/explorer/receipts
aitbc http call coordinator-api v1/explorer/receipts --params '{"job_id": "job-abc123"}'

# Get a job's signed receipt (requires a client credential)
aitbc http call coordinator-api v1/jobs/job-abc123/receipt --api-key <client-key>
```

### API

```bash
curl "http://<coordinator>:8203/v1/explorer/receipts?job_id=<job-id>"  # or /v1/jobs/{job_id}/receipt
```

## Pricing

### How Pricing Works

- Jobs are priced in **compute units** (typically GPU seconds)
- Each model has a base rate per compute unit
- Final price = `units × rate`

### Current Rates

| Model | Rate (AITBC/unit) | Typical Job Cost |
|-------|-------------------|------------------|
| `llama3.2` | 2.0 | 2-10 AITBC |
| `llama3.2:1b` | 0.5 | 0.5-2 AITBC |
| `codellama` | 2.5 | 3-15 AITBC |
| `stable-diffusion` | 5.0 | 10-50 AITBC |

*Rates may vary based on network demand and miner availability.*

## Getting the network tokens

### Via Exchange

1. Visit the Trade Exchange on the hub (`https://hub.aitbc.bubuit.net/` — the `website/` static UI)
2. Create an account or connect wallet
3. Send Ethereum to your deposit address
4. Receive AITBC at current exchange rate (1 ETH = 100,000 AITBC (example rate; oracle-driven in production))

See [Ethereum Wallet Setup](../architecture/6_trade-exchange.md) for detailed instructions.

### Via Mining

Earn AITBC by providing GPU compute:

- See [Miner Documentation](../architecture/4_blockchain-node.md)

## Verifying Receipts

Receipts are cryptographically signed to ensure authenticity.

### Signature Verification

```python
from aitbc_sdk.receipts import verify_receipt

receipt = get_receipt("rcpt-20260124-001234")
result = verify_receipt(receipt)   # -> ReceiptVerification
print(f"Receipt valid: {result.verified}")
```

### On-Chain Verification

Receipts can be anchored on-chain for permanent proof:

- ZK proofs enable privacy-preserving verification
- See [ZK Applications](../reference/5_zk-proofs.md)

## Payment Disputes

If you believe a payment was incorrect:

1. **Check the receipt** - Verify units and price match expectations
2. **Compare to job output** - Ensure you received the expected result
3. **Contact support** - If discrepancy exists, report via the platform

## Best Practices

1. **Monitor your balance** - Check before submitting large jobs
2. **Set spending limits** - Use API keys with rate limits
3. **Keep receipts** - Download important receipts for records
4. **Verify signatures** - For high-value transactions, verify cryptographically

## Next Steps

- Troubleshooting - Common payment issues
- Getting Started - Back to basics
