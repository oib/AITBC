---
title: Python SDK
description: Python SDK for AITBC platform integration
---

# Python SDK

The AITBC Python SDK provides a convenient way to interact with the AITBC platform from Python applications. It includes support for job management, marketplace operations, wallet management, and more.

## Installation

```bash
# Install from PyPI
pip install aitbc

# Or install from source
git clone https://github.com/aitbc/python-sdk.git
cd python-sdk
pip install -e .
```

## Quick Start

```python
from aitbc import AITBCClient

# Initialize the client
client = AITBCClient(
    api_key="your_api_key_here",
    base_url="https://api.aitbc.io"  # or http://localhost:8011 for dev
)

# Create a job
job = client.jobs.create({
    "name": "image-classification",
    "type": "ai-inference",
    "model": {
        "type": "python",
        "entrypoint": "model.py"
    }
})

# Wait for completion
result = client.jobs.wait_for_completion(job["job_id"])
print(f"Result: {result}")
```

## Configuration

### Environment Variables
```bash
export AITBC_API_KEY="your_api_key"
export AITBC_BASE_URL="https://api.aitbc.io"
export AITBC_NETWORK="mainnet"  # or testnet
```

### Code Configuration
```python
from aitbc import AITBCClient, Config

# Using Config object
config = Config(
    api_key="your_api_key",
    base_url="https://api.aitbc.io",
    timeout=30,
    retries=3
)

client = AITBCClient(config=config)
```

## Jobs API

### Create a Job

```python
# Basic job creation
job = client.jobs.create({
    "name": "my-ai-job",
    "type": "ai-inference",
    "model": {
        "type": "python",
        "entrypoint": "model.py",
        "requirements": ["numpy", "torch"]
    },
    "input": {
        "type": "image",
        "format": "jpeg"
    },
    "output": {
        "type": "json"
    },
    "resources": {
        "cpu": "1000m",
        "memory": "2Gi"
    },
    "pricing": {
        "max_cost": "0.10"
    }
})

print(f"Job created: {job['job_id']}")
```

### Upload Job Data

```python
# Upload input files
with open("input.jpg", "rb") as f:
    client.jobs.upload_input(job["job_id"], f, "image.jpg")

# Or upload multiple files
files = [
    ("image1.jpg", open("image1.jpg", "rb")),
    ("image2.jpg", open("image2.jpg", "rb"))
]
client.jobs.upload_inputs(job["job_id"], files)
```

### Monitor Job Progress

```python
# Get job status
status = client.jobs.get_status(job["job_id"])
print(f"Status: {status['status']}")

# Stream updates
for update in client.jobs.stream_updates(job["job_id"]):
    print(f"Update: {update}")

# Wait for completion with timeout
result = client.jobs.wait_for_completion(
    job["job_id"],
    timeout=300,  # 5 minutes
    poll_interval=5
)
```

### Get Results

```python
# Get job results
results = client.jobs.get_results(job["job_id"])
print(f"Results: {results}")

# Download output files
client.jobs.download_output(job["job_id"], "output/")
client.jobs.download_outputs(job["job_id"], "outputs/")  # All files
```

## Marketplace API

### List Available Offers

```python
# List all offers
offers = client.marketplace.list_offers()

# Filter by job type
offers = client.marketplace.list_offers(
    job_type="image-classification",
    max_price="0.01"
)

for offer in offers:
    print(f"Offer: {offer['offer_id']}, Price: {offer['price']}")
```

### Create and Manage Offers

```python
# Create an offer (as a miner)
offer = client.marketplace.create_offer({
    "job_type": "image-classification",
    "price": "0.001",
    "max_jobs": 10,
    "requirements": {
        "min_gpu_memory": "4Gi"
    }
})

# Update offer
client.marketplace.update_offer(
    offer["offer_id"],
    price="0.002"
)

# Cancel offer
client.marketplace.cancel_offer(offer["offer_id"])
```

### Accept Offers

```python
# Accept an offer for your job
transaction = client.marketplace.accept_offer(
    offer_id="offer_123",
    job_id="job_456",
    bid_price="0.001"
)

print(f"Transaction: {transaction['transaction_id']}")
```

## Wallet API

### Wallet Management

```python
# Create a new wallet
wallet = client.wallet.create()
print(f"Address: {wallet['address']}")

# Import existing wallet
wallet = client.wallet.import_private_key("your_private_key")

# Get wallet info
balance = client.wallet.get_balance()
address = client.wallet.get_address()
```

### Transactions

```python
# Send tokens
tx = client.wallet.send(
    to="0x123...",
    amount="1.0",
    token="AITBC"
)

# Stake tokens
client.wallet.stake(amount="100.0")

# Unstake tokens
client.wallet.unstake(amount="50.0")

# Get transaction history
history = client.wallet.get_transactions(limit=50)
```

## Receipts API

### Verify Receipts

```python
# Get a receipt
receipt = client.receipts.get(job_id="job_123")

# Verify a receipt
verification = client.receipts.verify(receipt)
print(f"Valid: {verification['valid']}")

# Verify with local verification
from aitbc.crypto import verify_receipt

is_valid = verify_receipt(receipt)
```

### Stream Receipts

```python
# Stream new receipts
for receipt in client.receipts.stream():
    print(f"New receipt: {receipt['receipt_id']}")
```

## WebSocket API

### Real-time Updates

```python
# Connect to WebSocket
ws = client.websocket.connect()

# Subscribe to job updates
ws.subscribe("jobs", job_id="job_123")

# Subscribe to marketplace updates
ws.subscribe("marketplace")

# Handle messages
@ws.on_message
def handle_message(message):
    print(f"Received: {message}")

# Start listening
ws.listen()
```

### Advanced WebSocket Usage

```python
# Custom event handlers
ws = client.websocket.connect()

@ws.on_job_update
def on_job_update(job_id, status):
    print(f"Job {job_id} status: {status}")

@ws.on_marketplace_update
def on_marketplace_update(update_type, data):
    print(f"Marketplace {update_type}: {data}")

# Run with context manager
with client.websocket.connect() as ws:
    ws.subscribe("jobs")
    ws.listen(timeout=60)
```

## Error Handling

```python
from aitbc.exceptions import (
    AITBCError,
    APIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError
)

try:
    job = client.jobs.create({...})
except AuthenticationError:
    print("Invalid API key")
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after} seconds")
except APIError as e:
    print(f"API error: {e.message}")
except AITBCError as e:
    print(f"AITBC error: {e}")
```

## Advanced Usage

### Custom HTTP Client

```python
import requests
from aitbc import AITBCClient

# Use custom session
session = requests.Session()
session.headers.update({"User-Agent": "MyApp/1.0"})

client = AITBCClient(
    api_key="your_key",
    session=session
)
```

### Async Support

```python
import asyncio
from aitbc import AsyncAITBCClient

async def main():
    client = AsyncAITBCClient(api_key="your_key")
    
    # Create job
    job = await client.jobs.create({...})
    
    # Wait for completion
    result = await client.jobs.wait_for_completion(job["job_id"])
    
    print(f"Result: {result}")

asyncio.run(main())
```

### Batch Operations

```python
# Create multiple jobs
jobs = [
    {"name": f"job-{i}", "type": "ai-inference"}
    for i in range(10)
]

created_jobs = client.jobs.create_batch(jobs)

# Get status of multiple jobs
statuses = client.jobs.get_status_batch([
    job["job_id"] for job in created_jobs
])
```

## Testing

### Mock Client for Testing

```python
from aitbc.testing import MockAITBCClient

# Use mock client for tests
client = MockAITBCClient()

# Configure responses
client.jobs.set_response("create", {"job_id": "test_job"})

# Test your code
job = client.jobs.create({...})
assert job["job_id"] == "test_job"
```

### Integration Tests

```python
import pytest
from aitbc import AITBCClient

@pytest.fixture
def client():
    return AITBCClient(
        api_key="test_key",
        base_url="http://localhost:8011"
    )

def test_job_creation(client):
    job = client.jobs.create({
        "name": "test-job",
        "type": "ai-inference"
    })
    assert "job_id" in job
```

## Best Practices

### 1. Configuration Management
```python
# Use environment variables
import os
from aitbc import AITBCClient

client = AITBCClient(
    api_key=os.getenv("AITBC_API_KEY"),
    base_url=os.getenv("AITBC_BASE_URL", "https://api.aitbc.io")
)
```

### 2. Error Handling
```python
# Always handle potential errors
try:
    result = client.jobs.get_results(job_id)
except NotFoundError:
    print("Job not found")
except APIError as e:
    print(f"API error: {e}")
```

### 3. Resource Management
```python
# Use context managers for resources
with client.jobs.upload_context(job_id) as ctx:
    ctx.upload_file("model.py")
    ctx.upload_file("requirements.txt")
```

### 4. Performance
```python
# Use async for concurrent operations
async def process_jobs(job_ids):
    client = AsyncAITBCClient(api_key="your_key")
    
    tasks = [
        client.jobs.get_results(job_id)
        for job_id in job_ids
    ]
    
    results = await asyncio.gather(*tasks)
    return results
```

## Examples

Check out the [examples directory](https://github.com/aitbc/python-sdk/tree/main/examples) for complete working examples:

- [Basic Job Submission](https://github.com/aitbc/python-sdk/blob/main/examples/basic_job.py)
- [Marketplace Bot](https://github.com/aitbc/python-sdk/blob/main/examples/marketplace_bot.py)
- [Mining Operation](https://github.com/aitbc/python-sdk/blob/main/examples/mining.py)
- [WebSocket Streaming](https://github.com/aitbc/python-sdk/blob/main/examples/websocket_streaming.py)

## Support

- 📖 [Documentation](../../)
- 🐛 [Issue Tracker](https://github.com/aitbc/python-sdk/issues)
- 💬 [Discord](https://discord.gg/aitbc)
- 📧 [python-sdk@aitbc.io](mailto:python-sdk@aitbc.io)

## Changelog

See [CHANGELOG.md](https://github.com/aitbc/python-sdk/blob/main/CHANGELOG.md) for version history and updates.
