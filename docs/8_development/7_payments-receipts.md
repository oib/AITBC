# Payments and Receipts

This guide explains how payments work on the AITBC network and how to understand your receipts.

## Payment Flow

```
Client submits job → Job processed by miner → Receipt generated → Payment settled
```

### Step-by-Step

1. **Job Submission**: You submit a job with your prompt and parameters
2. **Miner Selection**: The Coordinator assigns your job to an available miner
3. **Processing**: The miner executes your job using their GPU
4. **Receipt Creation**: A cryptographic receipt is generated proving work completion
5. **Settlement**: AITBC tokens are transferred from client to miner

## Understanding Receipts

Every completed job generates a receipt containing:

| Field | Description |
|-------|-------------|
| `receipt_id` | Unique identifier for this receipt |
| `job_id` | The job this receipt is for |
| `provider` | Miner address who processed the job |
| `client` | Your address (who requested the job) |
| `units` | Compute units consumed (e.g., GPU seconds) |
| `price` | Amount paid in AITBC tokens |
| `model` | AI model used |
| `started_at` | When processing began |
| `completed_at` | When processing finished |
| `signature` | Cryptographic proof of authenticity |

### Example Receipt

```json
{
  "receipt_id": "rcpt-20260124-001234",
  "job_id": "job-abc123",
  "provider": "ait1miner...",
  "client": "ait1client...",
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

Visit [Explorer → Receipts](https://aitbc.bubuit.net/explorer/#/receipts) to see:
- All recent receipts on the network
- Filter by your address to see your history
- Click any receipt for full details

### CLI

```bash
# List your receipts
./aitbc-cli.sh receipts

# Get specific receipt
./aitbc-cli.sh receipt <receipt_id>
```

### API

```bash
curl https://aitbc.bubuit.net/api/v1/receipts?client=<your_address>
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

## Getting AITBC Tokens

### Via Exchange

1. Visit [Trade Exchange](https://aitbc.bubuit.net/Exchange/)
2. Create an account or connect wallet
3. Send Bitcoin to your deposit address
4. Receive AITBC at current exchange rate (1 BTC = 100,000 AITBC)

See [Bitcoin Wallet Setup](BITCOIN-WALLET-SETUP.md) for detailed instructions.

### Via Mining

Earn AITBC by providing GPU compute:
- See [Miner Documentation](../6_architecture/4_blockchain-node.md)

## Verifying Receipts

Receipts are cryptographically signed to ensure authenticity.

### Signature Verification

```python
from aitbc_crypto import verify_receipt

receipt = get_receipt("rcpt-20260124-001234")
is_valid = verify_receipt(receipt)
print(f"Receipt valid: {is_valid}")
```

### On-Chain Verification

Receipts can be anchored on-chain for permanent proof:
- ZK proofs enable privacy-preserving verification
- See [ZK Applications](../5_reference/5_zk-proofs.md)

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

- [Troubleshooting](troubleshooting.md) - Common payment issues
- [Getting Started](getting-started.md) - Back to basics
