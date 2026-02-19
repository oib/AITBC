# AITBC SDK

Python client SDK for interacting with AITBC coordinator services, blockchain nodes, and marketplace components.

## Installation

```bash
pip install aitbc-sdk
```

## Quick Start

```python
import asyncio
from aitbc_sdk import AITBCClient

async def main():
    # Initialize client
    client = AITBCClient(base_url="https://aitbc.bubuit.net")
    
    # Submit a job
    job = await client.submit_job({
        "service_type": "llm_inference",
        "model": "llama3.2",
        "prompt": "Hello, world!"
    })
    
    # Check job status
    status = await client.get_job_status(job.id)
    print(f"Job status: {status.status}")
    
    # Get results when complete
    if status.status == "completed":
        result = await client.get_job_result(job.id)
        print(f"Result: {result.output}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Features

- **Job Management**: Submit, monitor, and retrieve computation jobs
- **Receipt Verification**: Cryptographically verify job completion receipts
- **Marketplace Integration**: Browse and participate in GPU marketplace
- **Blockchain Integration**: Interact with AITBC blockchain for settlement
- **Zero-Knowledge Support**: Private computation with ZK proof verification

## API Reference

### Client Initialization

```python
from aitbc_sdk import AITBCClient

client = AITBCClient(
    base_url="https://aitbc.bubuit.net",
    api_key="your-api-key",
    timeout=30
)
```

### Job Operations

```python
# Submit a job
job = await client.submit_job({
    "service_type": "llm_inference",
    "model": "llama3.2",
    "parameters": {
        "prompt": "Explain quantum computing",
        "max_tokens": 500
    }
})

# Get job status
status = await client.get_job_status(job.id)

# Get job result
result = await client.get_job_result(job.id)

# Cancel a job
await client.cancel_job(job.id)
```

### Receipt Operations

```python
# Get job receipts
receipts = await client.get_job_receipts(job.id)

# Verify receipt authenticity
is_valid = await client.verify_receipt(receipt)
```

### Marketplace Operations

```python
# List available services
services = await client.list_services()

# Get service details
service = await client.get_service(service_id)

# Place bid for computation
bid = await client.place_bid({
    "service_id": service_id,
    "max_price": 0.1,
    "requirements": {
        "gpu_memory": "8GB",
        "compute_capability": "7.5"
    }
})
```

## Configuration

The SDK can be configured via environment variables:

```bash
export AITBC_BASE_URL="https://aitbc.bubuit.net"
export AITBC_API_KEY="your-api-key"
export AITBC_TIMEOUT=30
```

## Development

Install in development mode:

```bash
git clone https://github.com/oib/AITBC.git
cd AITBC/packages/py/aitbc-sdk
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

## License

MIT License - see LICENSE file for details.

## Support

- **Documentation**: https://aitbc.bubuit.net/docs/
- **Issues**: https://github.com/oib/AITBC/issues
- **Discussions**: https://github.com/oib/AITBC/discussions
