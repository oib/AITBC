---
title: Code Examples
description: Practical examples for building on AITBC
---

# Code Examples

This section provides practical examples for common tasks on the AITBC platform.

## Python Examples

Two packages are involved, and which one you need depends on the task:

- **`aitbc-sdk`** (`packages/py/aitbc-sdk`) — synchronous. Health, wallet, registry, grants,
  signed receipts. No job-submission API.
- **`aitbc-agent-sdk`** (`packages/py/aitbc-agent-sdk`) — async. Job submission and status,
  via `ComputeConsumer`.

### Basic Job Submission

```python
import asyncio

from aitbc_agent import ComputeConsumer


async def main() -> None:
    consumer = ComputeConsumer.create(
        name="image-classifier",
        agent_type="consumer",
        capabilities={"compute_type": "inference"},
    )

    job_id = await consumer.submit_job(
        job_type="ai-inference",
        input_data={"model": "resnet50", "image_url": "https://example.com/cat.jpg"},
        requirements={"gpu_memory": 8},
        max_price=0.15,
    )

    status = await consumer.get_job_status(job_id)
    print(job_id, status)


asyncio.run(main())
```

### Batch Job Processing

```python
import asyncio

from aitbc_agent import ComputeConsumer


async def process_images(image_paths: list[str]) -> list[str]:
    consumer = ComputeConsumer.create(
        name="batch-processor",
        agent_type="consumer",
        capabilities={"compute_type": "inference"},
    )

    job_ids = await asyncio.gather(
        *(
            consumer.submit_job(
                job_type="image-analysis",
                input_data={"path": path},
            )
            for path in image_paths
        )
    )
    return list(job_ids)
```

`submit_job` returns a job id, not a result. There is no `wait_for_completion` helper — poll
`get_job_status(job_id)` until the status is terminal.

### Checking Receipts

```python
from aitbc_sdk import CoordinatorReceiptClient

with CoordinatorReceiptClient(base_url="http://localhost:8203", api_key="your_key") as rc:
    status = rc.summarize_receipts("job-123")
    print(status.verified_count, "of", status.total, "receipts verified")
    if status.has_failures:
        print(status.failure_reasons)
```

## CLI Examples

### Job Management

```bash
# Create job from file
aitbc job create job.yaml

# List all jobs
aitbc job list --status running

# Monitor job progress
aitbc job watch <job_id>

# Download results
aitbc job download <job_id> --output ./results/
```

### Marketplace Operations

```bash
# List available offers
aitbc marketplace list --type image-classification

# Create offer as miner
aitbc marketplace create-offer offer.yaml

# Accept offer
aitbc marketplace accept <offer_id> --job-id <job_id>
```

## Complete Examples

Find full working examples in this repository:

- [cURL Examples](../api/examples/curl-examples.md) — direct HTTP calls against the coordinator and blockchain node APIs
