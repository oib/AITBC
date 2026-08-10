---
title: Code Examples
description: Practical examples for building on AITBC
---

# Code Examples

This section provides practical examples for common tasks on the AITBC platform.

## Python Examples

### Basic Job Submission
```python
from aitbc import AITBCClient

client = AITBCClient(api_key="your_key")

job = client.jobs.create({
    "name": "image-classification",
    "type": "ai-inference",
    "model": {
        "type": "python",
        "entrypoint": "model.py",
        "requirements": ["torch", "pillow"]
    }
})

result = client.jobs.wait_for_completion(job["job_id"])
```

### Batch Job Processing
```python
import asyncio
from aitbc import AsyncAITBCClient

async def process_images(image_paths):
    client = AsyncAITBCClient(api_key="your_key")

    tasks = []
    for path in image_paths:
        job = await client.jobs.create({
            "name": f"process-{path}",
            "type": "image-analysis"
        })
        tasks.append(client.jobs.wait_for_completion(job["job_id"]))

    results = await asyncio.gather(*tasks)
    return results
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
