# Frequently Asked Questions

This document provides answers to frequently asked questions about the AITBC platform.

> **Note:** For the current operational state and deployment status, see [Current Operational State](../infrastructure/CURRENT_OPERATIONAL_STATE.md). For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Table of Contents

- [General Questions](#general-questions)
- [Installation and Setup](#installation-and-setup)
- [API Usage](#api-usage)
- [Blockchain](#blockchain)
- [Mining](#mining)
- [Payments](#payments)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Performance](#performance)

## General Questions

### What is AITBC?

AITBC (Advanced Intelligence Training Blockchain Consortium) is a comprehensive blockchain platform that supports multiple use cases including AI compute resource trading, multi-chain blockchain operations, agent coordination, and enterprise-grade security. While GPU compute marketplace is one of its key capabilities, the platform also supports general blockchain operations, smart contracts, and decentralized applications.

### How does AITBC work?

AITBC uses blockchain technology to create a trustless marketplace for GPU compute. Miners register their GPUs, submit compute offers, and process jobs. Developers submit jobs which are matched with available miners. Payments are handled through smart contracts with escrow to ensure fair compensation.

### What are the main components?

- **Blockchain Node**: Maintains the decentralized ledger
- **Coordinator API**: Manages job submission and coordination
- **Marketplace Service**: Matches jobs with miners
- **Wallet Daemon**: Handles cryptographic operations
- **GPU Miner**: Processes AI jobs on GPUs

### Is AITBC open source?

Yes, AITBC is open source. The code is available on GitHub at https://github.com/oib/AITBC

### How can I contribute?

Contributions are welcome! Please see the [contributing guidelines](https://github.com/oib/AITBC/blob/main/CONTRIBUTING.md) for more information.

## Installation and Setup

### What are the system requirements?

**Minimum (Development):**
- CPU: 4 cores
- RAM: 8 GB
- Storage: 100 GB SSD
- Python 3.13+

**Recommended (Production):**
- CPU: 8+ cores
- RAM: 16+ GB
- Storage: 500 GB NVMe SSD
- GPU: NVIDIA RTX 3090 or better (for mining)

### How do I install AITBC?

See the [Deployment Guide](../deployment/comprehensive-guide.md) for detailed installation instructions for various scenarios.

### Can I run AITBC on Windows?

AITBC is designed for Linux (Debian/Ubuntu). While it may run on Windows with WSL, it's not officially supported. We recommend using a Linux environment for production deployments.

### What Python version do I need?

Python 3.13 or higher is required. Earlier versions are not supported.

### How do I update AITBC?

```bash
cd /opt/aitbc
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart aitbc-*
```

## API Usage

### How do I get an API key?

Register as a client through the Coordinator API:

```bash
curl -X POST http://localhost:8011/v1/clients/register \
  -H "Content-Type: application/json" \
  -d '{"name": "My Application"}'
```

The response will include your API key.

### What are the rate limits?

- Job submission: 100 requests per minute
- Job status queries: 1000 requests per minute
- Result retrieval: 500 requests per minute

See the [API Reference](../api/README.md) for more details.

### How do I submit a job?

```python
import aitbc_sdk

client = aitbc_sdk.Client(api_key="your-api-key")
job = client.submit_job(
    payload={"model": "llama2", "prompt": "Hello world"},
    ttl_seconds=900
)
```

See the [Python SDK Examples](../api/examples/python-sdk-examples.md) for more examples.

### How do I monitor job status?

You can poll the status endpoint or use WebSocket for real-time updates:

```python
# Polling
status = client.get_job(job_id)

# WebSocket
client.watch_job(job_id, callback=on_update)
```

### What happens if a job fails?

If a job fails, the state will be set to `FAILED` and an error message will be provided. The payment will be refunded if the job was paid.

### How long do jobs stay in the system?

Jobs expire based on their `ttl_seconds` parameter. The default is 900 seconds (15 minutes). You can specify a longer TTL up to 86400 seconds (24 hours).

## Blockchain

### What blockchain does AITBC use?

AITBC uses a custom blockchain optimized for GPU compute transactions. It supports smart contracts, zero-knowledge proofs, and fast transaction confirmation.

### How do I run a blockchain node?

See the [Deployment Guide](../deployment/comprehensive-guide.md#blockchain-node) for blockchain node setup instructions.

### How do I sync with the blockchain?

The blockchain node automatically syncs when started. You can check sync status:

```bash
curl http://localhost:8006/health
/opt/aitbc/aitbc-cli chain
```

### What if my node gets out of sync?

If your node gets out of sync, try the following:

1. Restart the blockchain node
2. Add bootstrap peers
3. Reset the blockchain state (last resort)

See the [Troubleshooting Guide](../troubleshooting/comprehensive-guide.md#blockchain-node-issues) for more details.

### How do I become a validator?

Validators require staking AITBC tokens. See the [Staking Documentation](../blockchain/staking.md) for more information.

## Mining

### What GPUs are supported?

NVIDIA GPUs with CUDA 12.4+ support are recommended. Tested GPUs include:
- NVIDIA RTX 3090
- NVIDIA RTX 4090
- NVIDIA A100
- NVIDIA H100

### How do I register as a miner?

```bash
curl -X POST http://localhost:8011/v1/miners/register \
  -H "Content-Type: application/json" \
  -d '{
    "miner_id": "miner-123",
    "gpu_type": "nvidia-rtx-3090",
    "gpu_memory": 24
  }'
```

### How do I start mining?

The mining process is automatic once you're registered. The Coordinator API will assign jobs to your miner based on your GPU specifications and job constraints.

### How are payments calculated?

Payments are based on:
- GPU type and memory
- Job duration
- Current market rates
- Quality of service

### How do I receive payments?

Payments are automatically sent to your wallet address when jobs are completed. You can specify your wallet address during miner registration.

### Can I mine with multiple GPUs?

Yes, you can register multiple GPUs by creating multiple miner registrations, each with a unique miner ID.

## Payments

### How do I make a payment for a job?

Include payment details when submitting a job:

```python
job = client.submit_job(
    payload={"model": "llama2", "prompt": "Hello"},
    payment_amount=100.0,
    payment_currency="AITBC"
)
```

### What is escrow?

Escrow holds the payment in a smart contract until the job is completed successfully. If the job fails, the payment is refunded automatically.

### What currencies are supported?

- AITBC (native token)
- ETH (via smart contract)
- USDC (via smart contract)

### How do I check payment status?

```bash
curl -H "X-Api-Key: $API_KEY" \
  http://localhost:8011/v1/jobs/{job_id}/payment
```

### What happens if a miner fails to complete a job?

If a miner fails to complete a job, the payment is refunded and the miner may be penalized or banned depending on the severity of the failure.

## Troubleshooting

### Service won't start

Check the service status and logs:

```bash
sudo systemctl status aitbc-coordinator-api
sudo journalctl -u aitbc-coordinator-api -n 50
```

See the [Troubleshooting Guide](../troubleshooting/comprehensive-guide.md) for more details.

### Database connection failed

1. Check PostgreSQL status: `sudo systemctl status postgresql`
2. Test connection: `psql -h localhost -U aitbc -d aitbc`
3. Check firewall rules

### GPU not detected

1. Check GPU: `nvidia-smi`
2. Check driver: `dmesg | grep -i nvidia`
3. Check CUDA: `nvcc --version`

### Jobs stuck in queued state

1. Check if miners are registered
2. Verify job constraints can be satisfied
3. Increase job TTL

See the [Troubleshooting Guide](../troubleshooting/comprehensive-guide.md) for comprehensive troubleshooting steps.

## Security

### How are API keys secured?

API keys should be stored securely using environment variables or secret management systems. Never commit API keys to code repositories.

### Is my data encrypted?

Yes, all data in transit is encrypted using TLS. Data at rest can be encrypted using disk encryption or database encryption.

### How do I secure my installation?

See the [Security Best Practices Guide](../security/best-practices.md) for comprehensive security recommendations.

### What should I do if I suspect a security breach?

1. Immediately stop all services
2. Rotate all credentials
3. Review logs for suspicious activity
4. Contact the security team
5. Restore from clean backup

## Performance

### How can I improve API performance?

1. Enable caching (Redis)
2. Optimize database queries
3. Use connection pooling
4. Enable compression
5. Use CDN for static assets

### How can I improve blockchain performance?

1. Increase peer connections
2. Optimize block size
3. Use SSD storage
4. Increase network bandwidth

### How can I improve mining performance?

1. Use faster GPU
2. Optimize job processing
3. Reduce overhead
4. Use GPU-specific optimizations

### What are the recommended hardware specifications?

See the [Deployment Guide](../deployment/comprehensive-guide.md#system-requirements) for detailed hardware recommendations.

## Additional Resources

- [API Reference](../api/README.md)
- [Deployment Guide](../deployment/comprehensive-guide.md)
- [Security Best Practices](../security/best-practices.md)
- [Troubleshooting Guide](../troubleshooting/comprehensive-guide.md)
- [GitHub Repository](https://github.com/oib/AITBC)
- [Community Forum](https://community.aitbc.dev/)

## Still Have Questions?

If you couldn't find the answer to your question, please:

1. Search the [documentation](../)
2. Check [GitHub Issues](https://github.com/oib/AITBC/issues)
3. Ask in the [community forum](https://community.aitbc.dev/)
4. Contact support at support@aitbc.dev
