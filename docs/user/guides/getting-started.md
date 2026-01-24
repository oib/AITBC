# Getting Started with AITBC

Welcome to the AI Token Blockchain (AITBC) network! This guide will help you get started as a user of the decentralized AI compute marketplace.

## What is AITBC?

AITBC is a decentralized marketplace that connects:
- **Clients** who need AI compute power (inference, training, image generation)
- **Miners** who provide GPU resources and earn AITBC tokens
- **Developers** who build applications on the platform

## Quick Start Options

### Option 1: Use the Web Interface

1. Visit [https://aitbc.bubuit.net](https://aitbc.bubuit.net)
2. Navigate to the **Marketplace** to browse available AI services
3. Connect your wallet or create an account
4. Submit your first AI job

### Option 2: Use the CLI

```bash
# Install the CLI wrapper
curl -O https://aitbc.bubuit.net/cli/aitbc-cli.sh
chmod +x aitbc-cli.sh

# Check available services
./aitbc-cli.sh status

# Submit a job
./aitbc-cli.sh submit "Your prompt here" --model llama3.2
```

### Option 3: Use the SDK

**Python:**
```python
from aitbc_sdk import AITBCClient

client = AITBCClient(api_url="https://aitbc.bubuit.net/api")
result = client.submit_job(
    prompt="Explain quantum computing",
    model="llama3.2"
)
print(result.output)
```

## Core Concepts

### Jobs
A job is a unit of work submitted to the network. It includes:
- **Prompt**: Your input (text, image, etc.)
- **Model**: The AI model to use (e.g., `llama3.2`, `stable-diffusion`)
- **Parameters**: Optional settings (temperature, max tokens, etc.)

### Receipts
After a job completes, you receive a **receipt** containing:
- Job ID and status
- Compute units consumed
- Miner who processed the job
- Cryptographic proof of completion

### Tokens
AITBC tokens are used to:
- Pay for compute jobs
- Reward miners for providing resources
- Participate in governance

## Your First Job

1. **Connect your wallet** at the Exchange or create an account
2. **Get some AITBC tokens** (see [Bitcoin Wallet Setup](BITCOIN-WALLET-SETUP.md))
3. **Submit a job** via web, CLI, or SDK
4. **Wait for completion** (typically seconds to minutes)
5. **View your receipt** in the Explorer

## Next Steps

- [Job Submission Workflow](job-submission.md) - Detailed guide on submitting jobs
- [Payments and Receipts](payments-receipts.md) - Understanding the payment flow
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [User Interface Guide](USER-INTERFACE-GUIDE.md) - Navigating the web interface

## Getting Help

- **Documentation**: [https://aitbc.bubuit.net/docs/](https://aitbc.bubuit.net/docs/)
- **Explorer**: [https://aitbc.bubuit.net/explorer/](https://aitbc.bubuit.net/explorer/)
- **API Reference**: [https://aitbc.bubuit.net/api/docs](https://aitbc.bubuit.net/api/docs)
