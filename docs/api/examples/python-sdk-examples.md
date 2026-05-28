# Python SDK Examples

This document provides comprehensive examples for using the AITBC Python SDK.

## Installation

```bash
pip install aitbc-sdk
```

## Basic Setup

```python
import aitbc_sdk

# Initialize client
client = aitbc_sdk.Client(
    api_key="your-api-key",
    base_url="http://localhost:8011"
)
```

## Job Submission

### Simple Job Submission

```python
# Submit a simple job
job = client.submit_job(
    payload={
        "model": "llama2",
        "prompt": "Hello, world!"
    },
    ttl_seconds=900
)

print(f"Job ID: {job.job_id}")
print(f"State: {job.state}")
```

### Job with Constraints

```python
# Submit job with GPU constraints
from aitbc_sdk import Constraints

job = client.submit_job(
    payload={
        "model": "llama2",
        "prompt": "Hello, world!"
    },
    constraints=Constraints(
        min_gpu_memory=8,
        gpu_type="nvidia-rtx-3090"
    ),
    ttl_seconds=900
)
```

### Job with Payment

```python
# Submit job with payment
job = client.submit_job(
    payload={
        "model": "llama2",
        "prompt": "Hello, world!"
    },
    payment_amount=100.0,
    payment_currency="AITBC",
    ttl_seconds=900
)

print(f"Payment ID: {job.payment_id}")
```

## Job Status Monitoring

### Get Job Status

```python
# Get current job status
status = client.get_job(job_id="your-job-id")
print(f"State: {status.state}")
print(f"Assigned Miner: {status.assigned_miner_id}")
print(f"Error: {status.error}")
```

### Poll for Completion

```python
import time

job_id = "your-job-id"

while True:
    status = client.get_job(job_id)
    print(f"State: {status.state}")
    
    if status.state in ["COMPLETED", "FAILED", "CANCELLED", "EXPIRED"]:
        break
    
    time.sleep(5)
```

### WebSocket for Real-time Updates

```python
# Monitor job status via WebSocket
def on_status_update(update):
    print(f"Status update: {update}")

client.watch_job(job_id="your-job-id", callback=on_status_update)
```

## Job Results

### Get Job Result

```python
# Get job result
result = client.get_job_result(job_id="your-job-id")
print(f"Output: {result.result}")
print(f"Receipt: {result.receipt}")
```

### Get Receipts

```python
# Get latest receipt
receipt = client.get_receipt(job_id="your-job-id")
print(f"Signature: {receipt.signature}")

# Get all receipts
receipts = client.list_receipts(job_id="your-job-id")
for receipt in receipts:
    print(f"Receipt: {receipt.signature}")
```

## Job Cancellation

```python
# Cancel a job
cancelled_job = client.cancel_job(job_id="your-job-id")
print(f"State: {cancelled_job.state}")
```

## Payment Operations

### Get Payment Status

```python
# Get payment information
payment = client.get_payment(job_id="your-job-id")
print(f"Status: {payment.status}")
print(f"Amount: {payment.amount}")
```

## Blockchain Operations

### Initialize Blockchain Client

```python
blockchain = aitbc_sdk.BlockchainClient(
    base_url="http://localhost:8006"
)
```

### Get Block Information

```python
# Get head block
head_block = blockchain.get_head_block()
print(f"Current height: {head_block.height}")

# Get block by height
block = blockchain.get_block(height=12345)
print(f"Block hash: {block.hash}")
```

### Network Status

```python
# Get network information
network = blockchain.get_network_info()
print(f"Peer count: {network.peer_count}")
print(f"Chain ID: {network.chain_id}")

# Get peers
peers = blockchain.get_peers()
for peer in peers:
    print(f"Peer: {peer.address}")
```

### Transaction Operations

```python
# Get transaction
tx = blockchain.get_transaction(tx_hash="0x...")
print(f"From: {tx.from}")
print(f"To: {tx.to}")
print(f"Value: {tx.value}")
```

## Error Handling

```python
from aitbc_sdk.exceptions import APIError, AuthenticationError

try:
    job = client.submit_job(
        payload={"model": "llama2", "prompt": "Hello"}
    )
except AuthenticationError:
    print("Invalid API key")
except APIError as e:
    print(f"API error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Advanced Examples

### Batch Job Submission

```python
# Submit multiple jobs
jobs = []
for prompt in ["Hello", "World", "Test"]:
    job = client.submit_job(
        payload={"model": "llama2", "prompt": prompt},
        ttl_seconds=900
    )
    jobs.append(job)

print(f"Submitted {len(jobs)} jobs")
```

### Job History

```python
# Get job history
history = client.get_job_history(limit=10)
for job in history:
    print(f"Job {job.job_id}: {job.state}")
```

### Custom Headers

```python
# Use custom headers
client = aitbc_sdk.Client(
    api_key="your-api-key",
    base_url="http://localhost:8011",
    headers={"X-Custom-Header": "value"}
)
```

## Testing

```python
# Mock client for testing
from unittest.mock import Mock

mock_client = Mock()
mock_client.submit_job.return_value = Mock(job_id="test-id", state="QUEUED")

job = mock_client.submit_job(payload={"model": "test"})
assert job.job_id == "test-id"
```

## Configuration

### Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()

client = aitbc_sdk.Client(
    api_key=os.getenv("AITBC_API_KEY"),
    base_url=os.getenv("AITBC_BASE_URL", "http://localhost:8011")
)
```

### Timeout Configuration

```python
client = aitbc_sdk.Client(
    api_key="your-api-key",
    base_url="http://localhost:8011",
    timeout=30  # 30 second timeout
)
```

## Receipt Verification

```python
import aitbc_crypto

# Verify receipt signature
receipt = client.get_receipt(job_id="your-job-id")
is_valid = aitbc_crypto.verify_receipt(
    receipt.signature,
    receipt.data,
    public_key="miner-public-key"
)

if is_valid:
    print("Receipt is valid")
else:
    print("Receipt is invalid")
```
